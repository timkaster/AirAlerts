"""Build analysis-ready air-alert datasets from a Telegram JSON export.

The input is the Telegram Desktop export format (`result.json`) for the
"Повітряна Тривога" public channel. Outputs are CSV files suitable for
exploratory analysis, forecasting baselines, and report tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


ALERT_EMOJIS = {"🔴", "🟢", "🟡"}
TIME_RE = re.compile(r"^\s*(?P<emoji>.)\s+(?P<clock>\d{1,2}:\d{2})\s+(?P<body>.+?)\s*$")
HASHTAG_RE = re.compile(r"#([\wА-Яа-яІіЇїЄєҐґʼ'’.-]+)", re.UNICODE)


@dataclass(frozen=True)
class Event:
    message_id: int
    event_datetime_utc: datetime
    event_datetime_kyiv: datetime
    event_date_kyiv: str
    event_hour_kyiv: int
    weekday_kyiv: str
    source_date: str
    emoji: str
    clock_text: str
    action: str
    threat_type: str
    location_name: str
    location_slug: str
    hashtags: str
    first_line: str
    parse_note: str


def last_sunday(year: int, month: int) -> int:
    cursor = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    while cursor.weekday() != 6:
        cursor -= timedelta(days=1)
    return cursor.day


def kyiv_datetime_from_utc(event_utc: datetime) -> datetime:
    """Convert UTC to Kyiv civil time without requiring the tzdata package.

    Ukraine uses UTC+2 in winter and UTC+3 during daylight saving time. For the
    period covered by this project, DST starts at 01:00 UTC on the last Sunday
    in March and ends at 01:00 UTC on the last Sunday in October.
    """
    year = event_utc.year
    dst_start = datetime(year, 3, last_sunday(year, 3), 1, 0, tzinfo=UTC)
    dst_end = datetime(year, 10, last_sunday(year, 10), 1, 0, tzinfo=UTC)
    offset_hours = 3 if dst_start <= event_utc < dst_end else 2
    return event_utc.astimezone(timezone(timedelta(hours=offset_hours), name="Europe/Kyiv"))


def flatten_text(value: Any) -> str:
    """Flatten Telegram rich text arrays into plain text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        return flatten_text(value.get("text", ""))
    return ""


def clean_location(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" .")
    return value


def slug_to_location(slug: str) -> str:
    value = slug.lstrip("#").replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return clean_location(value)


def normalize_slug(value: str) -> str:
    value = value.lstrip("#").strip()
    value = value.replace("'", "ʼ").replace("’", "ʼ")
    value = re.sub(r"\s+", "_", value)
    return value


def extract_hashtags(text: str) -> list[str]:
    return [match.group(1) for match in HASHTAG_RE.finditer(text)]


def location_candidates(
    location_name: str,
    hashtags: list[str],
    force_hashtags: bool,
) -> list[tuple[str, str, str]]:
    """Return `(location_name, location_slug, parse_note)` candidates."""
    if force_hashtags and hashtags:
        note = "multi_location_from_hashtags" if len(hashtags) > 1 else "location_from_hashtag"
        return [(slug_to_location(tag), normalize_slug(tag), note) for tag in hashtags]

    if location_name:
        slug = normalize_slug(hashtags[-1]) if hashtags else normalize_slug(location_name)
        note = "" if hashtags else "slug_from_location"
        return [(location_name, slug, note)]

    if hashtags:
        note = "multi_location_from_hashtags" if len(hashtags) > 1 else "location_from_hashtag"
        return [(slug_to_location(tag), normalize_slug(tag), note) for tag in hashtags]

    return []


def parse_events(message: dict[str, Any]) -> list[Event]:
    if message.get("type") != "message":
        return []

    text = flatten_text(message.get("text")).strip()
    if not text:
        return []

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line or first_line[0] not in ALERT_EMOJIS:
        return []

    match = TIME_RE.match(first_line)
    if not match:
        return []

    emoji = match.group("emoji")
    clock_text = match.group("clock")
    body = match.group("body").strip()
    hashtags = extract_hashtags(text)
    location_name = ""
    force_hashtag_locations = False

    if body.startswith("Повітряна тривога в"):
        action = "start"
        threat_type = "air_raid"
        location_name = clean_location(body.removeprefix("Повітряна тривога в"))
        force_hashtag_locations = not location_name
    elif body == "Повітряна тривога!":
        action = "start"
        threat_type = "air_raid"
        force_hashtag_locations = True
    elif body.startswith("Відбій тривоги в"):
        action = "end"
        threat_type = "air_raid"
        location_name = clean_location(body.removeprefix("Відбій тривоги в"))
        force_hashtag_locations = not location_name
    elif "Відбій повітряної тривоги" in body:
        action = "end"
        threat_type = "air_raid"
        force_hashtag_locations = True
    elif "Загроза артобстрілу" in body:
        action = "start"
        threat_type = "artillery_shelling"
        force_hashtag_locations = True
    elif "Відбій загрози артобстрілу в " in body:
        action = "end"
        threat_type = "artillery_shelling"
        location_name = clean_location(body.split("Відбій загрози артобстрілу в ", 1)[1])
    else:
        return []

    candidates = location_candidates(location_name, hashtags, force_hashtag_locations)
    if not candidates:
        return []

    unix_time = int(message["date_unixtime"])
    event_utc = datetime.fromtimestamp(unix_time, tz=UTC)
    event_kyiv = kyiv_datetime_from_utc(event_utc)

    return [
        Event(
            message_id=int(message["id"]),
            event_datetime_utc=event_utc,
            event_datetime_kyiv=event_kyiv,
            event_date_kyiv=event_kyiv.date().isoformat(),
            event_hour_kyiv=event_kyiv.hour,
            weekday_kyiv=event_kyiv.strftime("%A"),
            source_date=str(message.get("date", "")),
            emoji=emoji,
            clock_text=clock_text,
            action=action,
            threat_type=threat_type,
            location_name=candidate_name,
            location_slug=candidate_slug,
            hashtags=";".join(hashtags),
            first_line=first_line,
            parse_note=candidate_note,
        )
        for candidate_name, candidate_slug, candidate_note in candidates
    ]


def parse_event(message: dict[str, Any]) -> Event | None:
    """Backward-compatible helper for quick validation snippets."""
    events = parse_events(message)
    return events[0] if events else None


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def event_to_row(event: Event) -> dict[str, Any]:
    return {
        "message_id": event.message_id,
        "event_datetime_utc": event.event_datetime_utc.isoformat(),
        "event_datetime_kyiv": event.event_datetime_kyiv.isoformat(),
        "event_date_kyiv": event.event_date_kyiv,
        "event_hour_kyiv": event.event_hour_kyiv,
        "weekday_kyiv": event.weekday_kyiv,
        "source_date": event.source_date,
        "emoji": event.emoji,
        "clock_text": event.clock_text,
        "action": event.action,
        "threat_type": event.threat_type,
        "location_name": event.location_name,
        "location_slug": event.location_slug,
        "hashtags": event.hashtags,
        "first_line": event.first_line,
        "parse_note": event.parse_note,
    }


def build_intervals(events: list[Event]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    intervals: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    open_alerts: dict[tuple[str, str], Event] = {}

    for event in sorted(events, key=lambda item: (item.event_datetime_utc, item.message_id)):
        key = (event.location_slug, event.threat_type)

        if event.action == "start":
            if key in open_alerts:
                prior = open_alerts[key]
                unmatched.append(
                    {
                        "message_id": prior.message_id,
                        "event_datetime_kyiv": prior.event_datetime_kyiv.isoformat(),
                        "action": prior.action,
                        "threat_type": prior.threat_type,
                        "location_name": prior.location_name,
                        "location_slug": prior.location_slug,
                        "reason": "start_without_end_before_next_start",
                    }
                )
            open_alerts[key] = event
            continue

        start = open_alerts.pop(key, None)
        if start is None:
            unmatched.append(
                {
                    "message_id": event.message_id,
                    "event_datetime_kyiv": event.event_datetime_kyiv.isoformat(),
                    "action": event.action,
                    "threat_type": event.threat_type,
                    "location_name": event.location_name,
                    "location_slug": event.location_slug,
                    "reason": "end_without_prior_start",
                }
            )
            continue

        duration = event.event_datetime_utc - start.event_datetime_utc
        duration_minutes = duration.total_seconds() / 60
        if duration_minutes < 0:
            unmatched.append(
                {
                    "message_id": event.message_id,
                    "event_datetime_kyiv": event.event_datetime_kyiv.isoformat(),
                    "action": event.action,
                    "threat_type": event.threat_type,
                    "location_name": event.location_name,
                    "location_slug": event.location_slug,
                    "reason": "negative_duration",
                }
            )
            continue
        if duration_minutes < 1:
            duration_quality = "very_short_under_1_min"
        elif duration_minutes > 1440:
            duration_quality = "long_over_24h"
        else:
            duration_quality = "ok"

        intervals.append(
            {
                "location_slug": start.location_slug,
                "location_name": start.location_name,
                "threat_type": start.threat_type,
                "start_message_id": start.message_id,
                "end_message_id": event.message_id,
                "start_datetime_utc": start.event_datetime_utc.isoformat(),
                "end_datetime_utc": event.event_datetime_utc.isoformat(),
                "start_datetime_kyiv": start.event_datetime_kyiv.isoformat(),
                "end_datetime_kyiv": event.event_datetime_kyiv.isoformat(),
                "start_date_kyiv": start.event_date_kyiv,
                "end_date_kyiv": event.event_date_kyiv,
                "start_hour_kyiv": start.event_hour_kyiv,
                "duration_minutes": round(duration_minutes, 2),
                "duration_hours": round(duration_minutes / 60, 3),
                "duration_quality": duration_quality,
            }
        )

    for event in open_alerts.values():
        unmatched.append(
            {
                "message_id": event.message_id,
                "event_datetime_kyiv": event.event_datetime_kyiv.isoformat(),
                "action": event.action,
                "threat_type": event.threat_type,
                "location_name": event.location_name,
                "location_slug": event.location_slug,
                "reason": "start_still_open_at_export_end",
            }
        )

    return intervals, unmatched


def iter_local_day_segments(start_iso: str, end_iso: str) -> list[tuple[str, float]]:
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    segments: list[tuple[str, float]] = []
    cursor = start

    while cursor < end:
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=cursor.tzinfo)
        segment_end = min(end, next_midnight)
        minutes = (segment_end - cursor).total_seconds() / 60
        segments.append((cursor.date().isoformat(), minutes))
        cursor = segment_end

    return segments


def build_daily_summary(events: list[Event], intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    started_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    active_minutes: dict[tuple[str, str, str], float] = defaultdict(float)
    names: dict[tuple[str, str], str] = {}

    for event in events:
        names[(event.location_slug, event.threat_type)] = event.location_name
        if event.action == "start":
            started_counts[(event.event_date_kyiv, event.location_slug, event.threat_type)] += 1

    for interval in intervals:
        loc = str(interval["location_slug"])
        threat_type = str(interval["threat_type"])
        names[(loc, threat_type)] = str(interval["location_name"])
        for date, minutes in iter_local_day_segments(
            str(interval["start_datetime_kyiv"]), str(interval["end_datetime_kyiv"])
        ):
            active_minutes[(date, loc, threat_type)] += minutes

    keys = sorted(set(started_counts) | set(active_minutes))
    rows: list[dict[str, Any]] = []
    for date, loc, threat_type in keys:
        rows.append(
            {
                "date_kyiv": date,
                "location_slug": loc,
                "location_name": names.get((loc, threat_type), slug_to_location(loc)),
                "threat_type": threat_type,
                "alerts_started": started_counts.get((date, loc, threat_type), 0),
                "active_minutes": round(active_minutes.get((date, loc, threat_type), 0.0), 2),
                "active_hours": round(active_minutes.get((date, loc, threat_type), 0.0) / 60, 3),
            }
        )
    return rows


def build_location_summary(intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for interval in intervals:
        grouped[(str(interval["location_slug"]), str(interval["threat_type"]))].append(interval)

    rows: list[dict[str, Any]] = []
    for (loc, threat_type), items in sorted(grouped.items()):
        durations = [float(item["duration_minutes"]) for item in items]
        rows.append(
            {
                "location_slug": loc,
                "location_name": str(items[-1]["location_name"]),
                "threat_type": threat_type,
                "interval_count": len(items),
                "total_duration_minutes": round(sum(durations), 2),
                "total_duration_hours": round(sum(durations) / 60, 3),
                "mean_duration_minutes": round(mean(durations), 2),
                "median_duration_minutes": round(median(durations), 2),
                "max_duration_minutes": round(max(durations), 2),
                "first_start_kyiv": min(str(item["start_datetime_kyiv"]) for item in items),
                "last_end_kyiv": max(str(item["end_datetime_kyiv"]) for item in items),
            }
        )
    return rows


def write_data_dictionary(path: Path, source_path: Path, counts: dict[str, int]) -> None:
    body = f"""# Processed Air Alert Dataset

Generated from Telegram Desktop export:
`{source_path}`

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

- Parsed alert events: {counts["events"]}
- Paired intervals: {counts["intervals"]}
- Clean paired intervals: {counts["clean_intervals"]}
- Unmatched events: {counts["unmatched"]}
- Daily summary rows: {counts["daily_rows"]}
- Clean daily summary rows: {counts["clean_daily_rows"]}
- Location summary rows: {counts["location_rows"]}
- Clean location summary rows: {counts["clean_location_rows"]}

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
"""
    path.write_text(body, encoding="utf-8")


def build_dataset(source_path: Path, output_dir: Path) -> None:
    with source_path.open("r", encoding="utf-8") as handle:
        export = json.load(handle)

    events = [
        event
        for message in export.get("messages", [])
        for event in parse_events(message)
    ]
    event_rows = [event_to_row(event) for event in events]
    intervals, unmatched = build_intervals(events)
    clean_intervals = [row for row in intervals if row["duration_quality"] == "ok"]
    daily_rows = build_daily_summary(events, intervals)
    clean_daily_rows = build_daily_summary(events, clean_intervals)
    location_rows = build_location_summary(intervals)
    clean_location_rows = build_location_summary(clean_intervals)

    write_csv(
        output_dir / "telegram_alert_events.csv",
        event_rows,
        [
            "message_id",
            "event_datetime_utc",
            "event_datetime_kyiv",
            "event_date_kyiv",
            "event_hour_kyiv",
            "weekday_kyiv",
            "source_date",
            "emoji",
            "clock_text",
            "action",
            "threat_type",
            "location_name",
            "location_slug",
            "hashtags",
            "first_line",
            "parse_note",
        ],
    )
    write_csv(
        output_dir / "alert_intervals.csv",
        intervals,
        [
            "location_slug",
            "location_name",
            "threat_type",
            "start_message_id",
            "end_message_id",
            "start_datetime_utc",
            "end_datetime_utc",
            "start_datetime_kyiv",
            "end_datetime_kyiv",
            "start_date_kyiv",
            "end_date_kyiv",
            "start_hour_kyiv",
            "duration_minutes",
            "duration_hours",
            "duration_quality",
        ],
    )
    write_csv(
        output_dir / "alert_intervals_clean.csv",
        clean_intervals,
        [
            "location_slug",
            "location_name",
            "threat_type",
            "start_message_id",
            "end_message_id",
            "start_datetime_utc",
            "end_datetime_utc",
            "start_datetime_kyiv",
            "end_datetime_kyiv",
            "start_date_kyiv",
            "end_date_kyiv",
            "start_hour_kyiv",
            "duration_minutes",
            "duration_hours",
            "duration_quality",
        ],
    )
    write_csv(
        output_dir / "daily_location_summary.csv",
        daily_rows,
        [
            "date_kyiv",
            "location_slug",
            "location_name",
            "threat_type",
            "alerts_started",
            "active_minutes",
            "active_hours",
        ],
    )
    write_csv(
        output_dir / "daily_location_summary_clean.csv",
        clean_daily_rows,
        [
            "date_kyiv",
            "location_slug",
            "location_name",
            "threat_type",
            "alerts_started",
            "active_minutes",
            "active_hours",
        ],
    )
    write_csv(
        output_dir / "location_summary.csv",
        location_rows,
        [
            "location_slug",
            "location_name",
            "threat_type",
            "interval_count",
            "total_duration_minutes",
            "total_duration_hours",
            "mean_duration_minutes",
            "median_duration_minutes",
            "max_duration_minutes",
            "first_start_kyiv",
            "last_end_kyiv",
        ],
    )
    write_csv(
        output_dir / "location_summary_clean.csv",
        clean_location_rows,
        [
            "location_slug",
            "location_name",
            "threat_type",
            "interval_count",
            "total_duration_minutes",
            "total_duration_hours",
            "mean_duration_minutes",
            "median_duration_minutes",
            "max_duration_minutes",
            "first_start_kyiv",
            "last_end_kyiv",
        ],
    )
    write_csv(
        output_dir / "unmatched_events.csv",
        unmatched,
        [
            "message_id",
            "event_datetime_kyiv",
            "action",
            "threat_type",
            "location_name",
            "location_slug",
            "reason",
        ],
    )
    write_data_dictionary(
        output_dir / "DATA_DICTIONARY.md",
        source_path,
        {
            "events": len(event_rows),
            "intervals": len(intervals),
            "clean_intervals": len(clean_intervals),
            "unmatched": len(unmatched),
            "daily_rows": len(daily_rows),
            "clean_daily_rows": len(clean_daily_rows),
            "location_rows": len(location_rows),
            "clean_location_rows": len(clean_location_rows),
        },
    )

    print(f"Parsed alert events: {len(event_rows):,}")
    print(f"Paired intervals: {len(intervals):,}")
    print(f"Clean paired intervals: {len(clean_intervals):,}")
    print(f"Unmatched events: {len(unmatched):,}")
    print(f"Daily summary rows: {len(daily_rows):,}")
    print(f"Clean daily summary rows: {len(clean_daily_rows):,}")
    print(f"Location summary rows: {len(location_rows):,}")
    print(f"Clean location summary rows: {len(clean_location_rows):,}")
    print(f"Output directory: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(r"C:\Users\timka\Downloads\Telegram Desktop\ChatExport_2026-06-20\result.json"),
        help="Path to Telegram Desktop result.json export.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory for processed CSV outputs.",
    )
    args = parser.parse_args()
    build_dataset(args.source, args.output_dir)


if __name__ == "__main__":
    main()
