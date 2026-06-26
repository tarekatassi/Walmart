"""Render a self-contained HTML dashboard of the sleep analysis.

The output is a single ``index.html`` with every chart embedded as a base64
data URI, so the file is fully portable — open it offline, email it, drop it on
a static host, no companion files needed.
"""

from __future__ import annotations

import base64
import datetime as _dt
from pathlib import Path

from . import analysis, plots

# Friendly names + descriptions for each chart file plots.py emits.
_CHART_META = {
    "sleep_duration_trend.png": (
        "Sleep duration over time",
        "Hours asleep each night with a rolling average and the 7–9h target band.",
    ),
    "sleep_schedule.png": (
        "Bedtime & wake time",
        "When you fell asleep and woke — the spread shows how regular your schedule is.",
    ),
    "sleep_by_weekday.png": (
        "Sleep by day of week",
        "Average hours asleep per weekday (weekends highlighted).",
    ),
    "sleep_stages.png": (
        "Sleep stages",
        "Average time spent in each sleep stage per night.",
    ),
}


def _img_data_uri(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _metric_cards(stats: dict) -> str:
    avg_h = stats["avg_asleep_min"] / 60.0
    in_range = 7 <= avg_h <= 9
    cards = [
        ("Avg time asleep", analysis._fmt_hm(stats["avg_asleep_min"]),
         "ok" if in_range else "warn",
         f"median {analysis._fmt_hm(stats['median_asleep_min'])}"),
        ("Avg time in bed", analysis._fmt_hm(stats["avg_in_bed_min"]), "",
         f"{stats['nights']} nights"),
        ("Sleep efficiency", f"{stats['avg_efficiency'] * 100:.0f}%",
         "ok" if stats["avg_efficiency"] >= 0.85 else "warn", "asleep ÷ in bed"),
        ("Typical bedtime", analysis._fmt_clock(stats["avg_bedtime_hour"]), "",
         f"±{stats['bedtime_std_min']:.0f} min"),
        ("Typical wake", analysis._fmt_clock(stats["avg_waketime_hour"]), "",
         f"±{stats['waketime_std_min']:.0f} min"),
        ("Awakenings / night", f"{stats['avg_awakenings']:.1f}", "", "per night"),
    ]
    out = []
    for label, value, cls, sub in cards:
        out.append(
            f'<div class="card"><div class="card-label">{label}</div>'
            f'<div class="card-value {cls}">{value}</div>'
            f'<div class="card-sub">{sub}</div></div>'
        )
    return "\n".join(out)


def _weekday_table(wd) -> str:
    rows = []
    for day, r in wd.iterrows():
        if r.isna().all() or r["nights"] != r["nights"]:  # NaN check
            continue
        rows.append(
            f"<tr><td>{day}</td><td>{int(r['nights'])}</td>"
            f"<td>{analysis._fmt_hm(r['avg_asleep_min'])}</td>"
            f"<td>{analysis._fmt_clock(r['avg_bedtime_hour'])}</td>"
            f"<td>{r['avg_efficiency'] * 100:.0f}%</td></tr>"
        )
    return "\n".join(rows)


def build_dashboard(sessions, out_dir, window: int = 7) -> Path:
    """Generate charts and write a self-contained ``index.html`` dashboard.

    Returns the path to the written HTML file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chart_paths = plots.generate_all(sessions, out_dir, window=window)
    stats = analysis.summary_stats(sessions)
    wd = analysis.weekday_breakdown(sessions)
    skipped = analysis.excluded_nights(sessions)
    observations = analysis._observations(stats, wd)

    # Charts as portable embedded images, in a stable order.
    chart_by_name = {p.name: p for p in chart_paths}
    chart_blocks = []
    for name, (title, desc) in _CHART_META.items():
        if name not in chart_by_name:
            continue
        chart_blocks.append(
            f'<figure class="chart"><figcaption><h3>{title}</h3>'
            f"<p>{desc}</p></figcaption>"
            f'<img alt="{title}" src="{_img_data_uri(chart_by_name[name])}"></figure>'
        )

    obs_items = "\n".join(f"<li>{o.lstrip('- ')}</li>" for o in observations)
    excluded_note = (
        f'<p class="note">Excluded {skipped} nights with no recorded sleep '
        "(e.g. bedtime windows logged before sleep tracking was on).</p>"
        if skipped else ""
    )
    generated = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    html = _TEMPLATE.format(
        date_from=f"{stats['date_from']:%b %d, %Y}",
        date_to=f"{stats['date_to']:%b %d, %Y}",
        nights=stats["nights"],
        excluded_note=excluded_note,
        cards=_metric_cards(stats),
        charts="\n".join(chart_blocks),
        weekday_rows=_weekday_table(wd),
        observations=obs_items,
        window=window,
        generated=generated,
    )
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sleep Dashboard</title>
<style>
  :root {{
    --bg: #0f1424; --panel: #1a2138; --panel2: #222b47;
    --text: #e7ecf6; --muted: #9aa6c2; --accent: #5a8dee;
    --ok: #4cc38a; --warn: #f0a35e; --border: #2c3656;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
  header h1 {{ margin: 0 0 4px; font-size: 28px; }}
  header .range {{ color: var(--muted); margin: 0; }}
  .note {{ color: var(--warn); font-size: 13px; margin: 8px 0 0; }}
  .cards {{
    display: grid; gap: 14px; margin: 28px 0;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }}
  .card {{
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; padding: 16px 18px;
  }}
  .card-label {{ color: var(--muted); font-size: 13px; }}
  .card-value {{ font-size: 30px; font-weight: 650; margin: 6px 0 2px; }}
  .card-value.ok {{ color: var(--ok); }}
  .card-value.warn {{ color: var(--warn); }}
  .card-sub {{ color: var(--muted); font-size: 12px; }}
  section {{ margin-top: 36px; }}
  section h2 {{ font-size: 18px; border-bottom: 1px solid var(--border);
    padding-bottom: 8px; }}
  .charts {{ display: grid; gap: 20px; grid-template-columns: repeat(2, 1fr); }}
  @media (max-width: 760px) {{ .charts {{ grid-template-columns: 1fr; }} }}
  .chart {{
    margin: 0; background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; padding: 16px; overflow: hidden;
  }}
  .chart h3 {{ margin: 0 0 2px; font-size: 16px; }}
  .chart figcaption p {{ margin: 0 0 10px; color: var(--muted); font-size: 13px; }}
  .chart img {{ width: 100%; height: auto; border-radius: 8px;
    background: #fff; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--panel);
    border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }}
  th, td {{ padding: 10px 14px; text-align: left;
    border-bottom: 1px solid var(--border); }}
  th {{ background: var(--panel2); color: var(--muted); font-weight: 600;
    font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  ul.obs {{ background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; padding: 16px 16px 16px 36px; }}
  ul.obs li {{ margin: 6px 0; }}
  footer {{ margin-top: 40px; color: var(--muted); font-size: 12px;
    text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>😴 Sleep Dashboard</h1>
    <p class="range">{nights} nights analysed · {date_from} – {date_to}</p>
    {excluded_note}
  </header>

  <div class="cards">
    {cards}
  </div>

  <section>
    <h2>Charts</h2>
    <div class="charts">
      {charts}
    </div>
  </section>

  <section>
    <h2>By day of week</h2>
    <table>
      <thead><tr><th>Day</th><th>Nights</th><th>Avg asleep</th>
        <th>Avg bedtime</th><th>Efficiency</th></tr></thead>
      <tbody>
        {weekday_rows}
      </tbody>
    </table>
  </section>

  <section>
    <h2>Observations</h2>
    <ul class="obs">
      {observations}
    </ul>
  </section>

  <footer>
    Generated {generated} · {window}-night rolling average ·
    Built with the Apple Health sleep analysis tool
  </footer>
</div>
</body>
</html>
"""
