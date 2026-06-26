"""Aggregate sessions into the numbers a human actually cares about."""

from __future__ import annotations

import pandas as pd


def _fmt_hm(minutes: float) -> str:
    """Minutes -> '7h 32m'."""
    if pd.isna(minutes):
        return "n/a"
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h {m:02d}m"


def _fmt_clock(decimal_hour: float) -> str:
    """Decimal hour (possibly >24 for post-midnight) -> 'HH:MM'."""
    if pd.isna(decimal_hour):
        return "n/a"
    h = int(decimal_hour) % 24
    m = int(round((decimal_hour - int(decimal_hour)) * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    return f"{h:02d}:{m:02d}"


def stage_label(col: str) -> str:
    """'stage_rem_min' -> 'REM'."""
    return col.replace("stage_", "").replace("_min", "").upper()


def main_sleep(sessions: pd.DataFrame, require_sleep: bool = True) -> pd.DataFrame:
    """The main (longest) sleep per night — the basis for nightly trends.

    By default excludes nights with **no recorded sleep** (``asleep_min == 0``),
    which are bedtime-schedule artifacts (e.g. an iPhone "In Bed" window from
    before sleep tracking existed) rather than measured sleep.
    """
    main = sessions[sessions["is_main"]]
    if require_sleep:
        main = main[main["asleep_min"] > 0]
    return main.copy()


def excluded_nights(sessions: pd.DataFrame) -> int:
    """How many main nights were dropped for having no recorded sleep."""
    main = sessions[sessions["is_main"]]
    return int((main["asleep_min"] == 0).sum())


def summary_stats(sessions: pd.DataFrame) -> dict:
    """Headline averages over the main nightly sleeps."""
    main = main_sleep(sessions)
    return {
        "nights": int(len(main)),
        "date_from": main["date"].min(),
        "date_to": main["date"].max(),
        "avg_asleep_min": main["asleep_min"].mean(),
        "median_asleep_min": main["asleep_min"].median(),
        "std_asleep_min": main["asleep_min"].std(),
        "avg_in_bed_min": main["time_in_bed_min"].mean(),
        "avg_efficiency": main["efficiency"].mean(),
        "avg_bedtime_hour": main["bedtime_hour"].mean(),
        "avg_waketime_hour": main["waketime_hour"].mean(),
        "bedtime_std_min": main["bedtime_hour"].std() * 60,
        "waketime_std_min": main["waketime_hour"].std() * 60,
        "avg_awakenings": main["n_awakenings"].mean(),
    }


def weekday_breakdown(sessions: pd.DataFrame) -> pd.DataFrame:
    """Average asleep time, bedtime and efficiency per day of week."""
    main = main_sleep(sessions)
    order = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday",
    ]
    g = (
        main.groupby("weekday")
        .agg(
            nights=("asleep_min", "size"),
            avg_asleep_min=("asleep_min", "mean"),
            avg_bedtime_hour=("bedtime_hour", "mean"),
            avg_efficiency=("efficiency", "mean"),
        )
        .reindex(order)
    )
    return g


def stage_breakdown(sessions: pd.DataFrame) -> pd.Series:
    """Average minutes per sleep stage across main sleeps (only stages present).

    Prefers true staged data (REM/Deep/Core); falls back to Apple's
    undifferentiated "Asleep" stage when that's all a device recorded.
    """
    main = main_sleep(sessions)
    present = [c for c in ("stage_rem_min", "stage_deep_min", "stage_core_min")
               if c in main.columns and main[c].sum() > 0]
    if not present and "stage_asleep_min" in main.columns:
        present = ["stage_asleep_min"]
    return main[present].mean() if present else pd.Series(dtype=float)


def rolling_trend(sessions: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """Per-night asleep hours plus a rolling average, indexed by date."""
    main = main_sleep(sessions).sort_values("date")
    out = main[["date", "asleep_min"]].copy()
    out["asleep_hours"] = out["asleep_min"] / 60.0
    out["rolling"] = out["asleep_hours"].rolling(window, min_periods=1).mean()
    return out.set_index("date")


def build_report(sessions: pd.DataFrame, window: int = 7) -> str:
    """A plain-text/markdown summary of the analysis."""
    s = summary_stats(sessions)
    wd = weekday_breakdown(sessions)
    stages = stage_breakdown(sessions)
    skipped = excluded_nights(sessions)

    lines = [
        "# Sleep Analysis Summary",
        "",
        f"- Nights analysed: **{s['nights']}** "
        f"({s['date_from']:%Y-%m-%d} to {s['date_to']:%Y-%m-%d})",]
    if skipped:
        lines.append(
            f"- _(Excluded {skipped} nights with no recorded sleep — e.g. "
            "bedtime windows logged before sleep tracking was on.)_"
        )
    lines += [
        f"- Average time asleep: **{_fmt_hm(s['avg_asleep_min'])}** "
        f"(median {_fmt_hm(s['median_asleep_min'])}, "
        f"±{_fmt_hm(s['std_asleep_min'])} night to night)",
        f"- Average time in bed: **{_fmt_hm(s['avg_in_bed_min'])}**",
        f"- Sleep efficiency: **{s['avg_efficiency'] * 100:.1f}%** "
        "(asleep / in bed)",
        f"- Typical bedtime: **{_fmt_clock(s['avg_bedtime_hour'])}**, "
        f"wake **{_fmt_clock(s['avg_waketime_hour'])}**",
        f"- Schedule consistency: bedtime ±{s['bedtime_std_min']:.0f} min, "
        f"wake ±{s['waketime_std_min']:.0f} min",
        f"- Average awakenings per night: **{s['avg_awakenings']:.1f}**",
        "",
        "## Sleep stages (avg per night)",
    ]
    for name, val in stages.items():
        lines.append(f"- {stage_label(name)}: {_fmt_hm(val)}")

    lines += ["", "## By day of week", "", "| Day | Nights | Avg asleep | Avg bedtime | Efficiency |", "| --- | --- | --- | --- | --- |"]
    for day, row in wd.iterrows():
        if pd.isna(row["nights"]):
            continue
        lines.append(
            f"| {day} | {int(row['nights'])} | {_fmt_hm(row['avg_asleep_min'])} "
            f"| {_fmt_clock(row['avg_bedtime_hour'])} "
            f"| {row['avg_efficiency'] * 100:.0f}% |"
        )

    # A couple of friendly, data-driven observations.
    lines += ["", "## Observations", ""]
    lines.extend(_observations(s, wd))
    return "\n".join(lines)


def _observations(stats: dict, wd: pd.DataFrame) -> list[str]:
    obs = []
    avg_h = stats["avg_asleep_min"] / 60.0
    if avg_h < 7:
        obs.append(
            f"- You average {avg_h:.1f}h asleep — below the common 7–9h "
            "target for adults."
        )
    elif avg_h > 9:
        obs.append(f"- You average {avg_h:.1f}h asleep — on the long side.")
    else:
        obs.append(f"- You average {avg_h:.1f}h asleep — within the healthy range.")

    if stats["bedtime_std_min"] > 60:
        obs.append(
            f"- Your bedtime varies by ±{stats['bedtime_std_min']:.0f} min; "
            "a more regular bedtime tends to improve sleep quality."
        )
    else:
        obs.append("- Your bedtime is fairly consistent night to night. Nice.")

    wd_valid = wd.dropna(subset=["avg_asleep_min"])
    if not wd_valid.empty:
        best = wd_valid["avg_asleep_min"].idxmax()
        worst = wd_valid["avg_asleep_min"].idxmin()
        obs.append(
            f"- You sleep most after **{best}** nights and least after **{worst}** nights."
        )
    if stats["avg_efficiency"] < 0.85:
        obs.append(
            f"- Sleep efficiency is {stats['avg_efficiency'] * 100:.0f}% — time in bed "
            "awake is on the higher side."
        )
    return obs
