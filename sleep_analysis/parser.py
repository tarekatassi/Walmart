"""Parse Apple Health ``export.xml`` into a tidy table of sleep records.

Apple Health stores sleep as ``HKCategoryTypeIdentifierSleepAnalysis`` records.
Each record is a single time interval (start/end) tagged with a stage value, e.g.::

    <Record type="HKCategoryTypeIdentifierSleepAnalysis"
            sourceName="Apple Watch"
            startDate="2024-01-01 23:32:00 -0500"
            endDate="2024-01-02 00:14:00 -0500"
            value="HKCategoryValueSleepAnalysisAsleepCore"/>

A single night is therefore made of *many* records (one per stage segment).
We stream the file with ``iterparse`` so multi-hundred-MB exports stay cheap on
memory, keep only the sleep records, and return them as a DataFrame.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"

# Map Apple's verbose category values to short, friendly stage names.
# Anything starting with "Asleep" counts as actual sleep; "InBed" and "Awake"
# do not. The InBed/Asleep distinction is what lets us measure sleep efficiency.
STAGE_MAP = {
    "HKCategoryValueSleepAnalysisInBed": "InBed",
    "HKCategoryValueSleepAnalysisAwake": "Awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "Asleep",
    "HKCategoryValueSleepAnalysisAsleepCore": "Core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "Deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "REM",
}

ASLEEP_STAGES = {"Asleep", "Core", "Deep", "REM"}


def _short_stage(value: str) -> str:
    """Turn a raw HKCategoryValue... string into a short label."""
    return STAGE_MAP.get(value, value.replace("HKCategoryValueSleepAnalysis", ""))


def _row_from_attrs(attrs: dict) -> dict:
    start_raw = attrs.get("startDate")
    end_raw = attrs.get("endDate")
    return {
        "start": start_raw,
        "end": end_raw,
        "start_raw": start_raw,
        "end_raw": end_raw,
        "stage": _short_stage(attrs.get("value", "")),
        "source": attrs.get("sourceName", ""),
    }


def _parse_with_iterparse(xml_path: Path) -> list[dict]:
    """Stream a well-formed export.xml; memory stays flat regardless of size."""
    rows: list[dict] = []
    for _event, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag == "Record" and elem.get("type") == SLEEP_TYPE:
            rows.append(_row_from_attrs(elem.attrib))
        elem.clear()
    return rows


# Pull attribute="value" pairs out of a single <Record ...> tag.
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _parse_with_regex(xml_path: Path) -> list[dict]:
    """Scan line by line for sleep <Record> tags. Tolerates a non-well-formed
    file (e.g. a grep-extracted slice with no root element)."""
    rows: list[dict] = []
    with open(xml_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if SLEEP_TYPE not in line:
                continue
            attrs = dict(_ATTR_RE.findall(line))
            if attrs.get("type") == SLEEP_TYPE and attrs.get("startDate"):
                rows.append(_row_from_attrs(attrs))
    return rows


def parse_export(xml_path: str | Path) -> pd.DataFrame:
    """Read ``export.xml`` and return one row per sleep record.

    Returns a DataFrame with columns:
        start, end (tz-aware datetimes), stage, is_asleep,
        duration_min, source.
    Raises ``FileNotFoundError`` if the path is missing and ``ValueError`` if
    the file contains no sleep records.
    """
    xml_path = Path(xml_path)
    if not xml_path.exists():
        raise FileNotFoundError(
            f"Could not find {xml_path}. Export your data from the iPhone "
            "Health app (profile photo -> Export All Health Data) and unzip it; "
            "the file you want is named 'export.xml'."
        )

    try:
        rows = _parse_with_iterparse(xml_path)
    except ET.ParseError:
        # The file isn't a complete, well-formed XML document. This is exactly
        # what you get from a `grep`-extracted slice of a huge export (no root
        # element, possibly a truncated final line). Fall back to scanning each
        # <Record .../> line with a regex, which doesn't care about structure.
        rows = _parse_with_regex(xml_path)

    if not rows:
        raise ValueError(
            f"No sleep records found in {xml_path}. Make sure you sleep-track "
            "with an Apple Watch or a third-party app that writes to Health."
        )

    df = pd.DataFrame(rows)
    # Apple timestamps look like "2024-01-01 23:32:00 -0500".
    # We keep two views of every timestamp:
    #   * UTC (tz-aware)  -> correct ordering and durations across DST changes.
    #   * local wall-clock -> what time the *clock on the wall* read, which is
    #     what matters for "what time did I go to bed". The wall-clock reading
    #     is just the string with its trailing offset removed.
    df["start"] = pd.to_datetime(df["start"], utc=True)
    df["end"] = pd.to_datetime(df["end"], utc=True)
    df["start_local"] = pd.to_datetime(
        df["start_raw"].str.rsplit(" ", n=1).str[0]
    )
    df["end_local"] = pd.to_datetime(df["end_raw"].str.rsplit(" ", n=1).str[0])
    df["is_asleep"] = df["stage"].isin(ASLEEP_STAGES)
    df["duration_min"] = (df["end"] - df["start"]).dt.total_seconds() / 60.0
    df = df.drop(columns=["start_raw", "end_raw"])
    df = df.sort_values("start").reset_index(drop=True)
    return df
