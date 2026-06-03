"""Tests for the sleep-analysis pipeline, driven by generated sample data."""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sleep_analysis import analysis, plots
from sleep_analysis.parser import parse_export
from sleep_analysis.sample_data import generate_export
from sleep_analysis.sessions import _merge_minutes, build_sessions


@pytest.fixture(scope="module")
def export_xml(tmp_path_factory):
    path = tmp_path_factory.mktemp("data") / "export.xml"
    generate_export(path, nights=40, seed=1, end_date=datetime(2024, 6, 1))
    return path


@pytest.fixture(scope="module")
def sessions(export_xml):
    return build_sessions(parse_export(export_xml))


def test_merge_minutes_handles_overlap():
    # 0–60 min and an overlapping 30–90 min interval -> 90 unique minutes.
    assert _merge_minutes([(0, 3600), (1800, 5400)]) == pytest.approx(90.0)
    # Disjoint intervals add up.
    assert _merge_minutes([(0, 600), (1200, 1800)]) == pytest.approx(20.0)
    assert _merge_minutes([]) == 0.0


def test_parse_finds_records(export_xml):
    df = parse_export(export_xml)
    assert len(df) > 0
    assert {"start", "end", "stage", "is_asleep", "duration_min"} <= set(df.columns)
    # Local wall-clock must be preserved, not collapsed to UTC.
    assert "start_local" in df.columns
    assert df["is_asleep"].any()


def test_parse_missing_file():
    with pytest.raises(FileNotFoundError):
        parse_export("/nope/does_not_exist.xml")


def test_regex_fallback_on_grep_slice(export_xml, tmp_path):
    # Simulate `grep ...SleepAnalysis export.xml > slice.xml`: a file with only
    # the sleep Record lines and no enclosing root element (not valid XML).
    slice_path = tmp_path / "sleep_only.xml"
    with open(export_xml) as fin, open(slice_path, "w") as fout:
        for line in fin:
            if "HKCategoryTypeIdentifierSleepAnalysis" in line:
                fout.write(line)
    df = parse_export(slice_path)  # must succeed via the regex fallback
    # Same record count as parsing the full, well-formed export.
    assert len(df) == len(parse_export(export_xml))
    assert df["is_asleep"].any()


def test_sessions_built(sessions):
    assert not sessions.empty
    # ~one main sleep per night.
    assert 35 <= sessions["is_main"].sum() <= 40
    # Efficiency is a sensible fraction.
    eff = sessions.loc[sessions["is_main"], "efficiency"]
    assert (eff > 0.5).all() and (eff <= 1.0).all()
    # Asleep time never exceeds time in bed.
    main = sessions[sessions["is_main"]]
    assert (main["asleep_min"] <= main["time_in_bed_min"] + 1e-6).all()


def test_asleep_not_clobbered_by_unspecified_stage(tmp_path):
    # Regression: Apple's "AsleepUnspecified" maps to the label "Asleep", whose
    # stage column must NOT overwrite the headline total `asleep_min`. This
    # night mixes a staged Core block with an unspecified-asleep block.
    xml = tmp_path / "mixed.xml"
    xml.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<HealthData>\n'
        '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="W" '
        'startDate="2024-03-01 23:00:00 -0500" endDate="2024-03-02 01:00:00 -0500" '
        'value="HKCategoryValueSleepAnalysisAsleepCore"/>\n'
        '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="W" '
        'startDate="2024-03-02 01:00:00 -0500" endDate="2024-03-02 02:00:00 -0500" '
        'value="HKCategoryValueSleepAnalysisAsleepUnspecified"/>\n'
        "</HealthData>\n",
        encoding="utf-8",
    )
    s = build_sessions(parse_export(xml))
    row = s.iloc[0]
    # 2h Core + 1h unspecified = 3h total asleep, regardless of stage columns.
    assert row["asleep_min"] == pytest.approx(180.0)
    assert row["stage_core_min"] == pytest.approx(120.0)
    assert row["stage_asleep_min"] == pytest.approx(60.0)


def test_summary_stats(sessions):
    s = analysis.summary_stats(sessions)
    assert s["nights"] >= 35
    # Sample data targets ~7h, so the average should land in a human range.
    assert 5 * 60 < s["avg_asleep_min"] < 10 * 60
    assert 0 < s["avg_efficiency"] <= 1


def test_weekend_lie_in(sessions):
    # Sample data deliberately gives longer weekend sleeps.
    main = sessions[sessions["is_main"]]
    wk = main.groupby("is_weekend")["asleep_min"].mean()
    assert wk[True] > wk[False]


def test_report_is_markdown(sessions):
    report = analysis.build_report(sessions)
    assert report.startswith("# Sleep Analysis Summary")
    assert "By day of week" in report
    assert "Observations" in report


def test_plots_written(sessions, tmp_path):
    written = plots.generate_all(sessions, tmp_path)
    assert len(written) >= 3
    for p in written:
        assert p.exists() and p.stat().st_size > 0
