"""Generate a synthetic Apple Health ``export.xml`` for demos and tests.

The output mimics a real iOS 16+ export: staged sleep records (Core/Deep/REM
plus the occasional Awake), one realistic night at a time, with weekend
lie-ins and a bit of night-to-night jitter.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import quoteattr

# Repeating within-night stage pattern (minutes, stage). Roughly 90-min cycles.
_CYCLE = [
    ("Core", 30), ("Deep", 25), ("Core", 20), ("REM", 20),
    ("Core", 25), ("Deep", 15), ("Core", 20), ("REM", 25),
    ("Awake", 5),
]
_STAGE_VALUE = {
    "Core": "HKCategoryValueSleepAnalysisAsleepCore",
    "Deep": "HKCategoryValueSleepAnalysisAsleepDeep",
    "REM": "HKCategoryValueSleepAnalysisAsleepREM",
    "Awake": "HKCategoryValueSleepAnalysisAwake",
    "InBed": "HKCategoryValueSleepAnalysisInBed",
}


def _fmt(dt: datetime, offset: str = "-0500") -> str:
    return f"{dt:%Y-%m-%d %H:%M:%S} {offset}"


def generate_export(
    path: str | Path,
    nights: int = 60,
    seed: int = 7,
    end_date: datetime | None = None,
) -> Path:
    """Write a synthetic export.xml covering ``nights`` nights ending today."""
    rng = random.Random(seed)
    path = Path(path)
    end_date = end_date or datetime.now()

    records: list[str] = []
    for n in range(nights):
        day = end_date - timedelta(days=nights - 1 - n)
        is_weekend = day.weekday() >= 5

        # Bedtime ~23:00 weekdays / 00:00 weekends, plus jitter.
        base_bed = 23.0 + (1.0 if is_weekend else 0.0)
        bed_h = base_bed + rng.gauss(0, 0.5)
        bedtime = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            hours=bed_h
        )

        # An enclosing "In Bed" record, like the iPhone writes.
        # Weekends get a clear lie-in vs. weekday nights.
        target_sleep = (8.4 if is_weekend else 6.6) + rng.gauss(0, 0.5)
        in_bed_end = bedtime + timedelta(hours=target_sleep + rng.uniform(0.2, 0.6))
        records.append(_record("InBed", bedtime, in_bed_end))

        # Fill the night with repeating stage cycles until we hit the target.
        cursor = bedtime + timedelta(minutes=rng.uniform(5, 20))  # fall-asleep latency
        asleep_target = timedelta(hours=target_sleep)
        accumulated = timedelta()
        ci = 0
        while accumulated < asleep_target:
            stage, mins = _CYCLE[ci % len(_CYCLE)]
            mins = max(3, int(mins + rng.gauss(0, 3)))
            seg_end = cursor + timedelta(minutes=mins)
            records.append(_record(stage, cursor, seg_end))
            cursor = seg_end
            if stage != "Awake":
                accumulated += timedelta(minutes=mins)
            ci += 1

    _write(path, records)
    return path


def _record(stage: str, start: datetime, end: datetime) -> str:
    return (
        '  <Record type="HKCategoryTypeIdentifierSleepAnalysis" '
        f"sourceName={quoteattr('Apple Watch')} "
        f"startDate={quoteattr(_fmt(start))} "
        f"endDate={quoteattr(_fmt(end))} "
        f"value={quoteattr(_STAGE_VALUE[stage])}/>"
    )


def _write(path: Path, records: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<HealthData locale="en_US">\n')
        f.write("\n".join(records))
        f.write("\n</HealthData>\n")


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "sample_export.xml"
    generate_export(out)
    print(f"Wrote sample export to {out}")
