"""Analyze Apple Health sleep data.

Typical use::

    from sleep_analysis import parse_export, build_sessions, build_report

    df = parse_export("export.xml")
    sessions = build_sessions(df)
    print(build_report(sessions))
"""

from .analysis import build_report, summary_stats, weekday_breakdown
from .parser import parse_export
from .sessions import build_sessions

__all__ = [
    "parse_export",
    "build_sessions",
    "build_report",
    "summary_stats",
    "weekday_breakdown",
]
