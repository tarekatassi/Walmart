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
