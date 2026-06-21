# Processed Air Alert Dataset

Generated from Telegram Desktop export:
`C:\Users\timka\Downloads\Telegram Desktop\ChatExport_2026-06-20\result.json`

## Files

- `telegram_alert_events.csv`: one row per parsed start/end alert message.
- `alert_intervals.csv`: paired start/end intervals with durations.
- `alert_intervals_clean.csv`: paired intervals with `duration_quality = ok`; recommended for first-pass EDA/modeling.
- `daily_location_summary.csv`: daily Kyiv-time location summary with alert starts and active minutes.
- `daily_location_summary_clean.csv`: daily summary calculated from clean intervals.
- `location_summary.csv`: location-level duration summary by threat type.
- `location_summary_clean.csv`: location-level summary calculated from clean intervals.
- `unmatched_events.csv`: starts/ends that could not be paired cleanly.

## Generated Counts

- Parsed alert events: 314508
- Paired intervals: 156964
- Clean paired intervals: 155884
- Unmatched events: 580
- Daily summary rows: 54265
- Clean daily summary rows: 52318
- Location summary rows: 292
- Clean location summary rows: 283

## Key Fields

- `event_datetime_utc`: message timestamp from Telegram unix time, converted to UTC.
- `event_datetime_kyiv`: same timestamp converted to Europe/Kyiv.
- `action`: `start` or `end`.
- `threat_type`: currently `air_raid` or `artillery_shelling`.
- `location_name`: human-readable Ukrainian location text.
- `location_slug`: normalized Telegram hashtag/location key.
- `duration_minutes`: interval length between start and matching end.
- `duration_quality`: `ok`, `very_short_under_1_min`, or `long_over_24h`.
- `active_minutes`: minutes active on that Kyiv calendar date. Intervals crossing midnight are split across dates.

## Notes

- The raw Telegram export is not copied into the repository because it is large.
- Yellow messages are treated as `end` events for the specific location named in the message; the warning text says alerts may still continue elsewhere.
- Artillery start messages often do not include the location in the first line, so their location is derived from the Telegram hashtag.
- Some newer messages include several locations in one Telegram post; these are expanded into one event row per location.
- Clean files exclude intervals under 1 minute and over 24 hours. Review the full interval table before deciding whether long frontline-region alerts are signal or data-quality artifacts for your analysis.
- Unmatched events should be reviewed before final modeling; they can come from export boundaries, duplicate starts, missing historical context, or channel format changes.
