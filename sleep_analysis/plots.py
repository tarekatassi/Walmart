"""Charts for sleep patterns. Saves PNGs; no display backend required."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt

from . import analysis


def _clock_formatter(decimal_hour: float, _pos=None) -> str:
    h = int(decimal_hour) % 24
    m = int(round((decimal_hour - int(decimal_hour)) * 60))
    return f"{h:02d}:{m:02d}"


def plot_duration_trend(sessions, out_dir: Path, window: int = 7) -> Path:
    """Nightly sleep hours with a rolling average and the 7–9h target band."""
    trend = analysis.rolling_trend(sessions, window=window)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(trend.index, trend["asleep_hours"], width=0.9, color="#9ec5fe",
           label="Nightly sleep")
    ax.plot(trend.index, trend["rolling"], color="#1f4e8c", lw=2,
            label=f"{window}-night average")
    ax.axhspan(7, 9, color="#b7e4c7", alpha=0.35, label="7–9h target")
    ax.set_ylabel("Hours asleep")
    ax.set_title("Sleep duration over time")
    ax.legend(loc="upper right", fontsize=8)
    fig.autofmt_xdate()
    path = out_dir / "sleep_duration_trend.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_schedule(sessions, out_dir: Path) -> Path:
    """Bedtime and wake time over the period — shows schedule drift/regularity."""
    main = analysis.main_sleep(sessions).sort_values("date")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(main["date"], main["bedtime_hour"], "o-", ms=3, color="#5a189a",
            label="Bedtime")
    ax.plot(main["date"], main["waketime_hour"], "o-", ms=3, color="#f48c06",
            label="Wake time")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_clock_formatter))
    ax.set_title("Bedtime & wake time")
    ax.set_ylabel("Clock time")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    path = out_dir / "sleep_schedule.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_weekday(sessions, out_dir: Path) -> Path:
    """Average sleep duration by day of week."""
    wd = analysis.weekday_breakdown(sessions).dropna(subset=["avg_asleep_min"])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#f48c06" if d in ("Saturday", "Sunday") else "#5a8dee"
              for d in wd.index]
    ax.bar(wd.index, wd["avg_asleep_min"] / 60.0, color=colors)
    ax.set_ylabel("Avg hours asleep")
    ax.set_title("Average sleep by day of week (weekends in orange)")
    ax.axhline(7, color="grey", ls="--", lw=1, alpha=0.7)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    path = out_dir / "sleep_by_weekday.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_stages(sessions, out_dir: Path) -> Path | None:
    """Average minutes per sleep stage (skipped if no staged data exists)."""
    stages = analysis.stage_breakdown(sessions)
    if stages.empty or (len(stages) == 1 and "stage_asleep_min" in stages.index):
        return None  # only undifferentiated "Asleep" data — nothing to break down
    fig, ax = plt.subplots(figsize=(6, 6))
    labels = [analysis.stage_label(s) for s in stages.index]
    ax.pie(stages.values, labels=labels, autopct="%1.0f%%", startangle=90,
           colors=["#3a0ca3", "#4361ee", "#4cc9f0", "#b5179e"][: len(stages)])
    ax.set_title("Average time per sleep stage")
    path = out_dir / "sleep_stages.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def generate_all(sessions, out_dir: str | Path, window: int = 7) -> list[Path]:
    """Render every chart into ``out_dir`` and return the paths written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        plot_duration_trend(sessions, out_dir, window=window),
        plot_schedule(sessions, out_dir),
        plot_weekday(sessions, out_dir),
    ]
    stage_path = plot_stages(sessions, out_dir)
    if stage_path:
        paths.append(stage_path)
    return paths
