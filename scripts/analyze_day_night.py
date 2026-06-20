"""Analyze alert duration split between day and night."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "alert_intervals_clean.csv"


def parse_clock(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def classify_period(moment: datetime, day_start: time, night_start: time) -> str:
    current = moment.time()
    return "day" if day_start <= current < night_start else "night"


def next_boundary(moment: datetime, day_start: time, night_start: time) -> datetime:
    today = moment.date()
    boundaries = [
        datetime.combine(today, day_start),
        datetime.combine(today, night_start),
        datetime.combine(today + timedelta(days=1), day_start),
    ]
    for boundary in boundaries:
        if boundary > moment:
            return boundary
    return datetime.combine(today + timedelta(days=1), day_start)


def analyze(
    input_path: Path,
    location_slug: str,
    threat_type: str,
    end_day: date,
    days: int,
    day_start: time,
    night_start: time,
) -> dict[str, object]:
    start_day = end_day - timedelta(days=days - 1)
    window_start = datetime.combine(start_day, time.min)
    window_end = datetime.combine(end_day + timedelta(days=1), time.min)

    minutes: Counter[str] = Counter()
    starts: Counter[str] = Counter()
    per_day: dict[date, Counter[str]] = defaultdict(Counter)
    interval_count = 0
    location_name = location_slug

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["location_slug"] != location_slug:
                continue
            if threat_type != "all" and row["threat_type"] != threat_type:
                continue

            start = datetime.fromisoformat(row["start_datetime_kyiv"]).replace(tzinfo=None)
            end = datetime.fromisoformat(row["end_datetime_kyiv"]).replace(tzinfo=None)
            if end <= window_start or start >= window_end:
                continue

            location_name = row["location_name"]
            interval_count += 1
            if window_start <= start < window_end:
                starts[classify_period(start, day_start, night_start)] += 1

            cursor = max(start, window_start)
            clipped_end = min(end, window_end)
            while cursor < clipped_end:
                boundary = min(next_boundary(cursor, day_start, night_start), clipped_end)
                period = classify_period(cursor, day_start, night_start)
                segment_minutes = (boundary - cursor).total_seconds() / 60
                minutes[period] += segment_minutes
                per_day[cursor.date()][period] += segment_minutes
                cursor = boundary

    total_minutes = minutes["day"] + minutes["night"]
    total_starts = starts["day"] + starts["night"]

    return {
        "location_name": location_name,
        "location_slug": location_slug,
        "threat_type": threat_type,
        "start_day": start_day,
        "end_day": end_day,
        "days": days,
        "interval_count": interval_count,
        "day_hours": minutes["day"] / 60,
        "night_hours": minutes["night"] / 60,
        "total_hours": total_minutes / 60,
        "day_share": (minutes["day"] / total_minutes * 100) if total_minutes else 0,
        "night_share": (minutes["night"] / total_minutes * 100) if total_minutes else 0,
        "day_starts": starts["day"],
        "night_starts": starts["night"],
        "total_starts": total_starts,
        "day_start_share": (starts["day"] / total_starts * 100) if total_starts else 0,
        "night_start_share": (starts["night"] / total_starts * 100) if total_starts else 0,
        "day_days_with_alarm": sum(1 for counts in per_day.values() if counts["day"] > 0),
        "night_days_with_alarm": sum(1 for counts in per_day.values() if counts["night"] > 0),
        "top_day": sorted(((day, counts["day"] / 60) for day, counts in per_day.items()), key=lambda item: item[1], reverse=True)[:5],
        "top_night": sorted(((day, counts["night"] / 60) for day, counts in per_day.items()), key=lambda item: item[1], reverse=True)[:5],
        "day_start": day_start,
        "night_start": night_start,
    }


def render_markdown(result: dict[str, object]) -> str:
    day_hours = float(result["day_hours"])
    night_hours = float(result["night_hours"])
    days = int(result["days"])
    top_day = result["top_day"]
    top_night = result["top_night"]
    assert isinstance(top_day, list)
    assert isinstance(top_night, list)

    def rows(items: list[tuple[date, float]]) -> str:
        return "\n".join(f"- {day.isoformat()}: {hours:.2f}h" for day, hours in items)

    return f"""# Day/Night Alert Analysis

Location: {result["location_name"]} (`{result["location_slug"]}`)  
Threat type: `{result["threat_type"]}`  
Window: {result["start_day"]} to {result["end_day"]} ({days} days)  
Day definition: {result["day_start"]} to {result["night_start"]}; night is the remaining hours.

## Summary

- Total alarm duration: {float(result["total_hours"]):.2f}h
- Day duration: {day_hours:.2f}h ({float(result["day_share"]):.1f}%)
- Night duration: {night_hours:.2f}h ({float(result["night_share"]):.1f}%)
- Average day duration per calendar day: {day_hours / days:.2f}h
- Average night duration per calendar day: {night_hours / days:.2f}h
- Alarm starts: {result["total_starts"]} total; {result["day_starts"]} day ({float(result["day_start_share"]):.1f}%), {result["night_starts"]} night ({float(result["night_start_share"]):.1f}%)
- Days with day-time alarm activity: {result["day_days_with_alarm"]}
- Days with night-time alarm activity: {result["night_days_with_alarm"]}

## Highest Night Alarm Duration

{rows(top_night)}

## Highest Day Alarm Duration

{rows(top_day)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--location-slug", default="м_Київ")
    parser.add_argument("--threat-type", default="air_raid")
    parser.add_argument("--end-date", type=lambda value: datetime.strptime(value, "%Y-%m-%d").date(), default=date(2026, 6, 20))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--day-start", type=parse_clock, default=time(6, 0))
    parser.add_argument("--night-start", type=parse_clock, default=time(22, 0))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = analyze(
        input_path=args.input,
        location_slug=args.location_slug,
        threat_type=args.threat_type,
        end_day=args.end_date,
        days=args.days,
        day_start=args.day_start,
        night_start=args.night_start,
    )
    markdown = render_markdown(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
