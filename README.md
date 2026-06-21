# Air Alerts Project

Time-series analysis of air raid alerts in Ukraine, built from a Telegram export and enriched with weather and geocoded location features.

## What Is In The Repo

- `scripts/`: reproducible data preparation, plotting, geocoding, weather, and modeling scripts.
- `reports/`: generated analysis summaries and SVG figures.
- `data/processed/`: only selected compact final datasets are committed for reproducibility.
- `RESEARCH_LOG.md`: audit trail of data, methods, assumptions, and AI-assisted work.
- `AGENTS.md`: workflow notes for agentic development.

## Data Policy

Raw and large intermediate data are ignored by git. The Telegram export is local and should not be committed.

Committed processed files:

- `data/processed/DATA_DICTIONARY.md`
- `data/processed/daily_location_summary_clean.csv`
- `data/processed/location_summary_clean.csv`
- `data/processed/location_geocodes.csv`
- `data/processed/weather_daily_regions_open_meteo.csv`

Ignored but recreatable files include event-level parsed rows, full interval tables, temporary weather samples, and smoke-test outputs.

## Recreate Core Alert Data

Requires the Telegram export:

```powershell
python scripts\build_alert_dataset.py `
  --source "C:\Users\timka\Downloads\Telegram Desktop\ChatExport_2026-06-20\result.json" `
  --output-dir data\processed
```

## Run The Tkinter Graph App

```powershell
python scripts\tkinter_alert_app.py
```

The app lets you search/select an alert region, choose dates/threat type, and compare alarm hours with precipitation and cloudiness.

## Geocode Locations

```powershell
python scripts\geocode_alert_locations.py
```

This writes `data\processed\location_geocodes.csv` using cached, single-threaded OpenStreetMap Nominatim requests.

## Train Predictive Baseline

```powershell
python scripts\train_predictive_model.py
```

Outputs:

- `reports/predictive_model_air_raid.md`
- `reports/predictive_model_feature_importance.csv`

Current finding: recent alert history is much more predictive than weather variables in the held-out test window.

## Useful Reports

- `reports/predictive_model_air_raid.md`
- `reports/geocoding_summary.md`
- `reports/day_night_kyiv_last_90_days.md`
- `reports/weather_data_sources.md`
