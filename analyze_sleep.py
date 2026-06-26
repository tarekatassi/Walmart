#!/usr/bin/env python3
"""Analyze your Apple Health sleep data and produce a report + charts.

Quick start
-----------
1. On your iPhone: Health app -> tap your profile photo -> "Export All Health
   Data". AirDrop / email the zip to your computer and unzip it. You'll get an
   ``apple_health_export/export.xml`` file (it can be large — that's fine).

2. Run::

       python analyze_sleep.py --input path/to/export.xml

   No export yet? Try it on generated data first::

       python analyze_sleep.py --demo

Outputs land in ``--out`` (default ``sleep_output/``): a Markdown summary,
a per-night CSV, and PNG charts.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from sleep_analysis import build_report, build_sessions, parse_export
from sleep_analysis import dashboard
from sleep_analysis.sample_data import generate_export


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Analyze Apple Health sleep data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", help="Path to Apple Health export.xml")
    src.add_argument(
        "--demo", action="store_true",
        help="Run on generated sample data (no export needed)",
    )
    p.add_argument("--out", "-o", default="sleep_output",
                   help="Output directory (default: sleep_output)")
    p.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                   help="Only analyse nights on/after this date (e.g. to skip "
                        "early years before you wore a sleep tracker)")
    p.add_argument("--gap-hours", type=float, default=3.0,
                   help="Gap that separates two sleep sessions (default: 3.0)")
    p.add_argument("--window", type=int, default=7,
                   help="Rolling-average window in nights (default: 7)")
    p.add_argument("--no-plots", action="store_true", help="Skip chart generation")
    args = p.parse_args(argv)

    if args.demo:
        tmp = Path(tempfile.mkdtemp()) / "sample_export.xml"
        generate_export(tmp, nights=60)
        xml_path = tmp
        print(f"[demo] generated 60 nights of sample data at {xml_path}")
    else:
        xml_path = args.input

    try:
        print(f"Parsing {xml_path} ...")
        df = parse_export(xml_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"  found {len(df):,} sleep records")
    sessions = build_sessions(df, gap_hours=args.gap_hours)
    if args.since:
        before = len(sessions)
        sessions = sessions[sessions["date"] >= args.since].reset_index(drop=True)
        print(f"  --since {args.since}: kept {len(sessions)} of {before} sessions")
    n_main = int(sessions["is_main"].sum()) if not sessions.empty else 0
    print(f"  reconstructed {len(sessions)} sessions across {n_main} nights")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(sessions, window=args.window)
    (out_dir / "sleep_report.md").write_text(report, encoding="utf-8")
    sessions.to_csv(out_dir / "sleep_sessions.csv", index=False)

    if not args.no_plots:
        # build_dashboard renders the charts and bundles them, the summary,
        # the weekday table and observations into a single index.html.
        html_path = dashboard.build_dashboard(sessions, out_dir, window=args.window)
        for w in sorted(out_dir.glob("*.png")):
            print(f"  chart: {w}")
        print(f"  dashboard: {html_path}")

    print("\n" + report)
    print(f"\nDone. Output written to {out_dir}/")
    if not args.no_plots:
        print(f"Open the dashboard:  {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
