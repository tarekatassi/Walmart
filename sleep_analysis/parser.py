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

    rows: list[dict] = []
    # iterparse + clear() keeps memory flat regardless of file size.
    for _event, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag != "Record" or elem.get("type") != SLEEP_TYPE:
            elem.clear()
            continue
        start_raw = elem.get("startDate")
        end_raw = elem.get("endDate")
        rows.append(
            {
                "start": start_raw,
                "end": end_raw,
                "start_raw": start_raw,
                "end_raw": end_raw,
                "stage": _short_stage(elem.get("value", "")),
                "source": elem.get("sourceName", ""),
            }
        )
        elem.clear()

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
