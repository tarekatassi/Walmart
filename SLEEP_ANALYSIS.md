# Sleep Pattern Analysis (Apple Health)

A small Python tool that reads your **Apple Health** export, reconstructs your
nightly sleep, and produces a readable report plus charts of your sleep
patterns.

## What it tells you

- Average / median time **asleep** and **in bed**, with night-to-night variability
- **Sleep efficiency** (asleep ÷ in bed)
- Typical **bedtime** and **wake time**, and how consistent your schedule is
- Time spent in each **sleep stage** (REM / Deep / Core), when your device records them
- **By day of week** breakdown (e.g. weekend lie-ins)
- Plain-language **observations** (are you hitting 7–9h? is your bedtime drifting?)

Charts produced:

| File | Shows |
| --- | --- |
| `sleep_duration_trend.png` | Hours asleep per night + rolling average + 7–9h target band |
| `sleep_schedule.png` | Bedtime & wake time over the period |
| `sleep_by_weekday.png` | Average sleep by day of week (weekends highlighted) |
| `sleep_stages.png` | Average time per sleep stage (if staged data exists) |

## 1. Get your Apple Health export

On your iPhone:

1. Open the **Health** app.
2. Tap your **profile photo** (top-right).
3. Scroll down and tap **Export All Health Data**.
4. AirDrop / email the resulting `.zip` to your computer and unzip it.
5. Inside `apple_health_export/` you'll find **`export.xml`** — that's the file
   this tool reads. (It can be hundreds of MB; the parser streams it, so that's fine.)

> Sleep stages (REM/Deep/Core) require an Apple Watch or a third-party sleep app
> that writes staged data to Health. Without one you'll still get duration,
> bedtime, efficiency, etc. from "In Bed" / "Asleep" records.

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Run it

```bash
# On your real data:
python analyze_sleep.py --input path/to/export.xml

# No export yet? Try it on generated sample data first:
python analyze_sleep.py --demo
```

Outputs are written to `sleep_output/` (override with `--out`):

- **`index.html`** — a self-contained **dashboard** that bundles the summary
  metrics, all charts, the weekday table and observations into one page. Charts
  are embedded as base64, so the file is fully portable: open it offline, email
  it, or drop it on a static host — no companion files needed. Open it with
  `open sleep_output/index.html` (macOS).
- `sleep_report.md` — the same summary as plain Markdown
- `sleep_sessions.csv` — one row per night for your own analysis
- the PNG charts above

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--input`, `-i` | — | Path to `export.xml` (or a `grep`-extracted slice — see below) |
| `--demo` | — | Generate and analyze 60 nights of sample data |
| `--out`, `-o` | `sleep_output` | Output directory |
| `--since` | — | Only analyse nights on/after `YYYY-MM-DD` (e.g. skip years before you wore a sleep tracker) |
| `--gap-hours` | `3.0` | Gap that separates two sleep sessions |
| `--window` | `7` | Rolling-average window (nights) |
| `--no-plots` | off | Skip chart generation |

> Nights with **no recorded sleep** (an "In Bed" window but zero measured
> sleep — common before you owned a sleep tracker) are automatically excluded
> from the averages, and the count of excluded nights is noted in the report.

### Huge exports: analyse without moving the whole file

Apple's `export.xml` includes *all* health data and can be several GB. The
sleep records are a tiny slice you can pull out locally — no Python needed:

```bash
# macOS / Linux, from the folder containing export.xml
grep 'HKCategoryTypeIdentifierSleepAnalysis' export.xml > sleep_only.xml
```

`sleep_only.xml` will be a few MB. It isn't a complete XML document (no root
element), but `analyze_sleep.py` detects that and falls back to a line-by-line
parser, so you can point `--input` straight at it.

## Use it as a library

```python
from sleep_analysis import parse_export, build_sessions, build_report

df = parse_export("export.xml")        # one row per raw sleep record
sessions = build_sessions(df)          # one row per reconstructed night
print(build_report(sessions))          # markdown summary
sessions.to_csv("nights.csv")          # per-night table for your own analysis
```

## How it works

1. **`parser.py`** streams `export.xml` with `iterparse` (memory stays flat on
   huge files), keeps only `HKCategoryTypeIdentifierSleepAnalysis` records, and
   preserves both UTC time (for correct durations across DST) and local
   wall-clock time (for "what time did I go to bed").
2. **`sessions.py`** groups records into nights (splitting on gaps > 3h) and
   computes durations from the **union** of intervals, so overlapping records
   from multiple sources (iPhone + Watch) are never double-counted.
3. **`analysis.py`** aggregates nightly stats, weekday patterns and the report.
4. **`plots.py`** renders the charts headlessly.

## Tests

```bash
python -m pytest tests/test_sleep.py -q
```
