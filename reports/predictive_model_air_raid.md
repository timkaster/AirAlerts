# Predictive Model: Daily Alert Hours

Threat type: `air_raid`  
Target: same-day alert hours per selected location and date  
Locations: 40 highest-total locations  
Date span: 2022-03-15 to 2026-06-20  
Test window: 2025-12-23 to 2026-06-20  
Model: dependency-free linear SGD regressor with chronological validation  
Training: 4 epochs, learning rate 0.01  

## What The Model Is For

This is a predictive baseline for understanding which inputs help forecast alert hours. It is not a causal model: a feature can improve prediction without causing alarms, and a real cause can look weak if it is already captured by region/history.

Weather joined from `data\processed\weather_daily_regions_open_meteo.csv` (39,447 date-region rows).

## Test Metrics

- Rows in test window: 7,200
- Mean target: 9.926 h/day
- Mean prediction: 10.554 h/day
- RMSE: 4.973 h/day
- MAE: 3.097 h/day
- R2 vs train-mean baseline: 0.822

## Feature Importance By Permutation

Higher positive values mean the model got worse when that group was shuffled in the held-out test window, so that group helped prediction more. Negative or near-zero values mean the model did not rely on that feature group in this validation window.

| Rank | Feature group | RMSE increase when shuffled | Shuffled RMSE | Shuffled R2 |
|---:|---|---:|---:|---:|
| 1 | `history:lag7_mean` | 2.0450 | 7.0178 | 0.645 |
| 2 | `history:lag1_hours` | 0.8678 | 5.8405 | 0.754 |
| 3 | `weather:temperature` | 0.0157 | 4.9885 | 0.820 |
| 4 | `history:lag30_mean` | 0.0116 | 4.9844 | 0.821 |
| 5 | `history:lag1_starts` | 0.0081 | 4.9809 | 0.821 |
| 6 | `calendar:seasonality` | 0.0058 | 4.9786 | 0.821 |
| 7 | `calendar:weekend` | 0.0017 | 4.9745 | 0.821 |
| 8 | `weather:pressure` | 0.0013 | 4.9741 | 0.822 |
| 9 | `calendar:weekday` | 0.0007 | 4.9735 | 0.822 |
| 10 | `weather:missing` | 0.0000 | 4.9728 | 0.822 |
| 11 | `weather:wind` | -0.0005 | 4.9723 | 0.822 |
| 12 | `weather:humidity` | -0.0006 | 4.9721 | 0.822 |

Full CSV: `reports\predictive_model_feature_importance.csv`

## Reading The Result

Most important group in this run: `history:lag7_mean`.

Use this ranking as evidence about predictive usefulness, not causality. In this run, recent alert history is the strongest signal, which means alert activity is temporally persistent. Weather variables can still be interesting, but if their permutation scores are small, they are not adding much beyond the model's geography, calendar, and recent-alert context.

## Largest Positive Non-Region Coefficients

- `lag7_mean_hours`: 1.986
- `lag1_hours`: 1.201
- `weather_surface_pressure_mean`: 0.538
- `lag30_mean_hours`: 0.452
- `weekday=3`: 0.347
- `month=8`: 0.316
- `lag2_hours`: 0.246
- `weekday=2`: 0.239
- `weather_shortwave_radiation_sum`: 0.236
- `weekday=5`: 0.211
- `month=11`: 0.201
- `weekday=4`: 0.196

## Largest Negative Non-Region Coefficients

- `days_since_alarm_capped30`: -0.280
- `weather_temperature_mean_c`: -0.198
- `lag1_alert_starts`: -0.170
- `weather_humidity_mean_pct`: -0.089
- `is_weekend`: -0.073
- `weather_wind_speed_max`: -0.029
- `month=12`: -0.009
- `yesterday_had_alarm`: 0.013
- `weather_snowfall_mm`: 0.014
- `month=1`: 0.016
- `month=3`: 0.018
- `month=9`: 0.022
