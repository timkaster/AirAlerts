# Research Log

Project: Time series analysis of air raid alerts in Ukraine  
Started: 2026-06-20

## How To Use This Log

Record research and engineering decisions as the project evolves. The goal is to make the final analysis auditable: what data was used, why methods were selected, what assumptions were made, and where AI helped.

Suggested entry format:

```markdown
## YYYY-MM-DD - Short Title

Goal:

Sources:

Actions:

Assumptions:

Findings:

Risks / Next Steps:

AI Assistance:
```

## 2026-06-20 - Repository Setup

Goal:
Initialize the project repository and create working documentation for agentic development.

Sources:
- Stage 2 prompt screenshot describing the task: "Time Series Analysis of air raid alerts in Ukraine."

Actions:
- Initialized a Git repository.
- Added `AGENTS.md` with project workflow guidance.
- Added this research log for tracking sources, assumptions, findings, and AI-assisted decisions.
- Added `.gitignore` to keep local environments, IDE settings, data artifacts, and generated outputs out of version control.

Assumptions:
- The project will use Python.
- Air raid alert records will need careful treatment of timestamps, regions, missingness, duplicates, and event duration.
- The final submission should be understandable to evaluators who care about reasoning as much as model output.

Findings:
- The starting project folder contained only PyCharm metadata and a virtual environment.

Risks / Next Steps:
- Identify an authoritative data source for Ukraine air raid alerts.
- Define the target question: descriptive analysis, forecasting, anomaly detection, regional comparison, or a combination.
- Establish a reproducible data ingestion pipeline before modeling.

AI Assistance:
- Codex created initial repository documentation and research-log scaffolding.

## 2026-06-20 - Telegram Export To Processed Dataset

Goal:
Convert the Telegram Desktop export from the "Повітряна Тривога" public channel into analysis-ready CSV files for time-series work.

Sources:
- `C:\Users\timka\Downloads\Telegram Desktop\ChatExport_2026-06-20\result.json`

Actions:
- Added `scripts/build_alert_dataset.py`.
- Parsed Telegram rich-text messages into plain text.
- Extracted alert start/end events for `air_raid` and `artillery_shelling`.
- Expanded multi-location Telegram posts into one event row per location.
- Converted Telegram unix timestamps into UTC and Kyiv civil time.
- Paired start/end events into alert intervals with durations.
- Built full and clean interval tables, daily summaries, location summaries, and unmatched-event diagnostics.

Assumptions:
- Red alert messages are starts; green and yellow alert messages are clears for the named location.
- Yellow clear messages can be treated as an end event for the specific location even when alerts continue elsewhere.
- Hashtags are reliable fallback location keys when the first line omits the location or contains several locations.
- Intervals under 1 minute or over 24 hours should be flagged as lower-confidence for first-pass analysis.

Findings:
- Generated 314,508 parsed location-level alert events.
- Generated 156,964 paired intervals.
- Generated 155,884 clean paired intervals after excluding intervals under 1 minute and over 24 hours.
- Only 580 parsed events remained unmatched after pairing.

Risks / Next Steps:
- Review `unmatched_events.csv` and long-duration intervals before final modeling.
- Decide whether long frontline-region alerts represent real persistent danger states or source-format artifacts.
- Use clean interval and daily summary files for first-pass EDA, then compare conclusions against the full files.

AI Assistance:
- Codex designed and implemented the parser, generated the processed CSV files, and documented dataset caveats.

## 2026-06-20 - Historic Weather Data Source

Goal:
Find a daily historic weather source for Ukraine and implement a minimal fetch path for precipitation features.

Sources:
- Open-Meteo Historical Weather API documentation.
- ECMWF ERA5-Land documentation.
- NASA POWER Daily API documentation.
- Meteostat Python documentation.

Actions:
- Selected Open-Meteo as the practical first data source.
- Added `scripts/fetch_open_meteo_weather.py` to download daily precipitation for one requested region.
- Added a guardrail so weather requests must cover no more than 180 inclusive calendar days.
- Added `reports/weather_data_sources.md` explaining source tradeoffs.
- Tested Open-Meteo daily API access for Kyiv and a sample multi-region pull before narrowing the scope.

Assumptions:
- For the first project version, a regional representative point is acceptable as a weather proxy.
- If weather becomes central to the final claim, true oblast area averages should be produced from ERA5-Land and administrative boundaries.

Findings:
- Open-Meteo provides daily `precipitation_sum` suitable for a lightweight weather feature.
- Broad multi-region/multi-year pulls are unnecessary for the current analysis and can trigger rate limits.

Risks / Next Steps:
- Fetch precipitation only for the exact region and date window being analyzed.
- Keep weather requests at 180 days or less.
- Map alert locations to weather regions before modeling.

AI Assistance:
- Codex researched weather-data options, built the scoped Open-Meteo precipitation downloader, and documented source tradeoffs.
