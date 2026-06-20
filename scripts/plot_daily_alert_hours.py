"""Plot daily air-alert active hours from the processed dataset.

This script intentionally uses only the Python standard library and writes SVG,
so it can run in a fresh Python environment without plotting dependencies.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path


def rolling_mean(values: list[float], window: int) -> list[float]:
    result: list[float] = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        result.append(sum(values[start : index + 1]) / (index - start + 1))
    return result


def load_daily_hours(
    path: Path,
    threat_type: str,
    location_slug: str | None,
) -> tuple[list[date], list[float], int, str]:
    totals: dict[date, float] = defaultdict(float)
    locations: set[str] = set()
    location_name = ""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if threat_type != "all" and row["threat_type"] != threat_type:
                continue
            if location_slug and row["location_slug"] != location_slug:
                continue
            day = datetime.strptime(row["date_kyiv"], "%Y-%m-%d").date()
            totals[day] += float(row["active_hours"])
            locations.add(row["location_slug"])
            location_name = row["location_name"]

    if not totals:
        return [], [], len(locations), location_name

    first_day = min(totals)
    last_day = max(totals)
    days: list[date] = []
    hours: list[float] = []
    cursor = first_day
    while cursor <= last_day:
        days.append(cursor)
        hours.append(totals.get(cursor, 0.0))
        cursor += timedelta(days=1)

    return days, hours, len(locations), location_name


def nice_upper_bound(value: float) -> float:
    if value <= 0:
        return 1
    candidates = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
    for candidate in candidates:
        if value <= candidate:
            return float(candidate)
    return ((int(value) // 5000) + 1) * 5000.0


def make_points(days: list[date], values: list[float], width: int, height: int, max_y: float) -> str:
    min_day = days[0].toordinal()
    max_day = days[-1].toordinal()
    day_span = max(1, max_day - min_day)

    points: list[str] = []
    for day, value in zip(days, values):
        x = (day.toordinal() - min_day) / day_span * width
        y = height - (value / max_y * height)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def month_ticks(days: list[date], width: int) -> list[tuple[float, str]]:
    min_day = days[0].toordinal()
    max_day = days[-1].toordinal()
    day_span = max(1, max_day - min_day)
    ticks: list[tuple[float, str]] = []

    cursor = date(days[0].year, ((days[0].month - 1) // 3) * 3 + 1, 1)
    while cursor <= days[-1]:
        if cursor >= days[0]:
            x = (cursor.toordinal() - min_day) / day_span * width
            ticks.append((x, cursor.strftime("%Y-%m")))
        month = cursor.month + 3
        year = cursor.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        cursor = date(year, month, 1)
    return ticks


def render_svg(input_path: Path, output_path: Path, threat_type: str, location_slug: str | None) -> None:
    days, hours, location_count, location_name = load_daily_hours(input_path, threat_type, location_slug)
    if not days:
        raise ValueError(f"No rows found for threat_type={threat_type!r}, location_slug={location_slug!r}")

    smooth = rolling_mean(hours, 7)
    max_y = 24.0 if location_slug else nice_upper_bound(max(hours))

    canvas_w = 1600
    canvas_h = 820
    left = 110
    right = 50
    top = 95
    bottom = 95
    plot_w = canvas_w - left - right
    plot_h = canvas_h - top - bottom
    title_threat = "air raid alerts" if threat_type == "air_raid" else threat_type.replace("_", " ")
    title_location = location_name or "Ukraine"
    subtitle = (
        "Clean intervals; one location, so values are hours per day."
        if location_slug
        else f"Clean {title_threat} intervals; simultaneous alerts in different locations are summed. Locations: {location_count}."
    )

    daily_points = make_points(days, hours, plot_w, plot_h, max_y)
    rolling_points = make_points(days, smooth, plot_w, plot_h, max_y)

    y_ticks = [0, max_y * 0.25, max_y * 0.5, max_y * 0.75, max_y]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" viewBox="0 0 {canvas_w} {canvas_h}">',
        "<style>",
        "text{font-family:Segoe UI,Arial,sans-serif;fill:#202124}",
        ".small{font-size:20px;fill:#4f5b66}",
        ".tick{font-size:18px;fill:#5f6368}",
        ".grid{stroke:#dfe3e8;stroke-width:1}",
        "</style>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="45" font-size="30" font-weight="700">Daily alarm hours: {escape(title_location)}</text>',
        f'<text x="{left}" y="75" class="small">{escape(subtitle)}</text>',
    ]

    for value in y_ticks:
        y = top + plot_h - (value / max_y * plot_h)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 16}" y="{y + 6:.1f}" text-anchor="end">{value:,.0f}</text>')

    for x, label in month_ticks(days, plot_w):
        sx = left + x
        parts.append(f'<line class="grid" x1="{sx:.1f}" y1="{top}" x2="{sx:.1f}" y2="{top + plot_h}"/>')
        parts.append(
            f'<text class="tick" x="{sx:.1f}" y="{top + plot_h + 36}" text-anchor="middle" transform="rotate(35 {sx:.1f} {top + plot_h + 36})">{label}</text>'
        )

    parts.extend(
        [
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#202124" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#202124" stroke-width="1.5"/>',
            f'<g transform="translate({left} {top})">',
            f'<polyline points="{daily_points}" fill="none" stroke="#4C78A8" stroke-width="1.2" opacity="0.35"/>',
            f'<polyline points="{rolling_points}" fill="none" stroke="#E45756" stroke-width="3.4"/>',
            "</g>",
            f'<text x="{left + plot_w - 250}" y="{top + 32}" class="small"><tspan fill="#4C78A8">Daily total</tspan>  <tspan fill="#E45756">7-day average</tspan></text>',
            f'<text x="{left + plot_w / 2}" y="{canvas_h - 20}" class="small" text-anchor="middle">Kyiv date</text>',
            f'<text x="30" y="{top + plot_h / 2}" class="small" text-anchor="middle" transform="rotate(-90 30 {top + plot_h / 2})">Alarm hours per day</text>',
            "</svg>",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/daily_location_summary_clean.csv"),
        help="Processed daily summary CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/daily_alert_location_hours.svg"),
        help="Output SVG path.",
    )
    parser.add_argument(
        "--threat-type",
        choices=["all", "air_raid", "artillery_shelling"],
        default="air_raid",
        help="Threat type to plot.",
    )
    parser.add_argument(
        "--location-slug",
        default=None,
        help="Optional exact location_slug to plot, for example м_Київ.",
    )
    args = parser.parse_args()
    render_svg(args.input, args.output, args.threat_type, args.location_slug)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
