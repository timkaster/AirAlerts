# Predictive Model: Daily Alert Hours

## Short Answer

The model can predict daily alarm hours reasonably well, but the useful signal is mostly yesterday and the previous week of alarms. Weather features are present in the model, but they are weak compared with recent alarm history.

- The model mostly uses recent alarm history: Recent alarm level: previous 7-day average, Yesterday's alarm hours.
- Weather features were weak in this run; they did not materially improve the forecast.
- Treat this as predictive evidence, not proof of cause and effect.

## What Was Predicted

- Target: same-day alert hours for a selected location and date
- Threat type: `air_raid`
- Locations included: top 40 locations by total alert duration
- Training period: 2022-03-15 to 2025-12-22
- Test period: 2025-12-23 to 2026-06-20
- Model type: simple linear predictive baseline

Weather joined from `data\processed\weather_daily_regions_open_meteo.csv` (39,447 date-region rows).

## Most Important Inputs

The table shows what happens when each input group is shuffled in the test period. If shuffling a group makes the forecast much worse, the model was relying on that information.

| Rank | Input tested | Effect on prediction | Extra error when shuffled |
|---:|---|---|---:|
| 1 | Recent alarm level: previous 7-day average | very strong | +2.045 h/day |
| 2 | Yesterday's alarm hours | meaningful | +0.868 h/day |
| 3 | Weather: temperature | tiny/negligible | +0.016 h/day |
| 4 | Recent alarm level: previous 30-day average | tiny/negligible | +0.012 h/day |
| 5 | Yesterday's number of alarm starts | tiny/negligible | +0.008 h/day |
| 6 | Seasonal position in the year | tiny/negligible | +0.006 h/day |
| 7 | Weekend flag | tiny/negligible | +0.002 h/day |
| 8 | Weather: pressure | tiny/negligible | +0.001 h/day |
| 9 | Day of week | tiny/negligible | +0.001 h/day |
| 10 | Weather data availability | tiny/negligible | +0.000 h/day |

Most important input group in this run: **Recent alarm level: previous 7-day average**.

## How Good Was It?

- Test rows: 7,200
- Actual average: 9.93 alarm hours/day
- Predicted average: 10.55 alarm hours/day
- Average absolute error: 3.10 hours/day
- Typical large-error scale: 4.97 hours/day
- Improvement over a simple average baseline: 82.2%

Plain English: the model captures broad patterns well, but day-to-day errors can still be several hours. That is expected for this kind of problem.

## Interpretation

This model is useful for understanding which inputs help prediction. It is not a causal model. A feature can help prediction without causing alarms, and a real cause can look weak if its effect is already captured by recent alarm history or region.

In this run, recent alert history is the strongest signal. That means alarm activity is temporally persistent: if a region had many alarm hours recently, the next day is more predictable from that recent pattern.

Weather variables can still be explored, but they are not strong predictors here. Their small permutation scores mean precipitation, temperature, wind, pressure, humidity, and related weather fields added little once the model already knew location, calendar, and recent alarms.

## Technical Details

- Validation method: chronological holdout, not random split
- Training: 4 epochs, learning rate 0.01
- Importance method: held-out permutation importance
- Full importance CSV: `reports\predictive_model_feature_importance.csv`

## Model Coefficients

These are secondary diagnostics, not the main conclusion. Positive values push predictions upward; negative values push them downward.

Largest upward signals:
- previous 7-day average alarm hours: +1.986
- yesterday's alarm hours: +1.201
- surface pressure: +0.538
- previous 30-day average alarm hours: +0.452
- Thursday: +0.347
- August: +0.316
- alarm hours two days ago: +0.246
- Wednesday: +0.239

Largest downward signals:
- days since last alarm, capped at 30: -0.280
- mean temperature: -0.198
- yesterday's number of alarm starts: -0.170
- mean humidity: -0.089
- weekend: -0.073
- max wind speed: -0.029
- December: -0.009
