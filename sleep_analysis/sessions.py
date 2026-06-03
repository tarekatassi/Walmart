"""Turn raw sleep records into nightly sleep sessions with metrics.

A single night produces many records (one per stage segment), sometimes from
several sources at once (e.g. an iPhone "In Bed" record overlapping an Apple
Watch staged record). We:

1. Group records into *sessions* by splitting wherever there is a gap longer
   than ``gap_hours`` between one record ending and the next starting.
2. For each session, compute durations from the **union** of intervals so
   overlapping records from different sources are never double-counted.
3. Attribute each session to the calendar date you *woke up* and flag the
   night's main (longest) sleep so naps don't distort nightly trends.
"""

from __future__ import annotations

import pandas as pd

from .parser import ASLEEP_STAGES

_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


def _epoch_seconds(series: pd.Series) -> pd.Series:
    """Tz-aware datetimes -> float seconds since epoch, independent of the
    underlying datetime resolution (pandas 3.0 defaults to microseconds, not
    nanoseconds, so a raw ``astype('int64')`` would be mis-scaled)."""
    return (series - _EPOCH).dt.total_seconds()


def _merge_minutes(intervals: list[tuple[float, float]]) -> float:
    """Total minutes covered by a set of [start, end] epoch-second intervals,
    counting overlapping regions only once."""
    if not intervals:
        return 0.0
    intervals = sorted(intervals)
    total = 0.0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start > cur_end:  # disjoint -> bank the current run
            total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:  # overlapping/adjacent -> extend
            cur_end = max(cur_end, end)
    total += cur_end - cur_start
    return total / 60.0


def _bedtime_hour(ts: pd.Timestamp) -> float:
    """Decimal local hour, unwrapped so post-midnight bedtimes sort after
    evening ones (22:00 -> 22.0, 00:30 -> 24.5, 01:00 -> 25.0)."""
    h = ts.hour + ts.minute / 60.0
    return h if h >= 12 else h + 24.0


def build_sessions(df: pd.DataFrame, gap_hours: float = 3.0) -> pd.DataFrame:
    """Build a per-session DataFrame from parsed sleep records.

    One row per session with columns:
        date, bedtime, waketime, bedtime_hour, waketime_hour,
        time_in_bed_min, asleep_min, efficiency, <stage>_min for each stage,
        n_awakenings, is_main, weekday, is_weekend.
    """
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("start").reset_index(drop=True)
    secs = _epoch_seconds(df["start"])
    end_secs = _epoch_seconds(df["end"])
    gap = gap_hours * 3600.0

    # Assign a session id: new session whenever this record starts more than
    # `gap` after the latest end seen so far in the running session.
    session_ids = []
    sid = 0
    running_end = end_secs.iloc[0]
    for i in range(len(df)):
        if i > 0 and secs.iloc[i] - running_end > gap:
            sid += 1
            running_end = end_secs.iloc[i]
        else:
            running_end = max(running_end, end_secs.iloc[i])
        session_ids.append(sid)
    df = df.assign(session=session_ids)

    all_stages = sorted(df["stage"].unique())
    records = []
    for _sid, g in df.groupby("session"):
        asleep = g[g["is_asleep"]]
        in_bed_intervals = list(
            zip(_epoch_seconds(g["start"]), _epoch_seconds(g["end"]))
        )
        asleep_intervals = list(
            zip(_epoch_seconds(asleep["start"]), _epoch_seconds(asleep["end"]))
        )
        time_in_bed = _merge_minutes(in_bed_intervals)
        asleep_min = _merge_minutes(asleep_intervals)

        bedtime = g["start_local"].min()
        waketime = g["end_local"].max()

        row = {
            "date": waketime.date(),
            "bedtime": bedtime,
            "waketime": waketime,
            "bedtime_hour": _bedtime_hour(bedtime),
            "waketime_hour": waketime.hour + waketime.minute / 60.0,
            "time_in_bed_min": round(time_in_bed, 1),
            "asleep_min": round(asleep_min, 1),
            "efficiency": round(asleep_min / time_in_bed, 3) if time_in_bed else 0.0,
            # Awake segments inside the session ~ number of awakenings.
            "n_awakenings": int((g["stage"] == "Awake").sum()),
            "source": g["source"].mode().iloc[0] if not g["source"].mode().empty else "",
        }
        # Per-stage minutes. Namespaced with a "stage_" prefix so a stage label
        # (e.g. Apple's unspecified "Asleep") can never collide with a headline
        # metric column such as "asleep_min".
        for stage in all_stages:
            sg = g[g["stage"] == stage]
            ivals = list(zip(_epoch_seconds(sg["start"]), _epoch_seconds(sg["end"])))
            row[f"stage_{stage.lower()}_min"] = round(_merge_minutes(ivals), 1)
        records.append(row)

    sessions = pd.DataFrame(records).sort_values("bedtime").reset_index(drop=True)

    # Flag the main (longest asleep) session for each wake-up date.
    sessions["is_main"] = False
    idx_main = sessions.groupby("date")["asleep_min"].idxmax()
    sessions.loc[idx_main, "is_main"] = True

    sessions["date"] = pd.to_datetime(sessions["date"])
    sessions["weekday"] = sessions["date"].dt.day_name()
    sessions["is_weekend"] = sessions["date"].dt.dayofweek >= 5
    return sessions
