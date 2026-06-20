"""Tkinter app for graphing daily alert hours by region.

Run from PyCharm with the project interpreter:

    python scripts/tkinter_alert_app.py

The app uses only the Python standard library.
"""

from __future__ import annotations

import csv
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "daily_location_summary_clean.csv"
DEFAULT_LOCATION_SLUG = "м_Київ"


@dataclass(frozen=True)
class DailyRow:
    day: date
    location_slug: str
    location_name: str
    threat_type: str
    active_hours: float


def parse_day(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def load_rows(path: Path) -> list[DailyRow]:
    rows: list[DailyRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                DailyRow(
                    day=parse_day(raw["date_kyiv"]),
                    location_slug=raw["location_slug"],
                    location_name=raw["location_name"],
                    threat_type=raw["threat_type"],
                    active_hours=float(raw["active_hours"]),
                )
            )
    return rows


def rolling_mean(values: list[float], window: int = 7) -> list[float]:
    result: list[float] = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        result.append(sum(values[start : index + 1]) / (index - start + 1))
    return result


def build_location_choices(rows: list[DailyRow]) -> tuple[list[str], dict[str, str]]:
    names_by_slug: dict[str, str] = {}
    for row in rows:
        names_by_slug.setdefault(row.location_slug, row.location_name)

    def sort_key(item: tuple[str, str]) -> tuple[int, str]:
        slug, name = item
        return (0 if slug == DEFAULT_LOCATION_SLUG else 1, name.casefold())

    choices: list[str] = []
    slug_by_choice: dict[str, str] = {}
    for slug, name in sorted(names_by_slug.items(), key=sort_key):
        label = f"{name} ({slug})"
        choices.append(label)
        slug_by_choice[label] = slug
    return choices, slug_by_choice


def make_series(
    rows: list[DailyRow],
    location_slug: str,
    threat_type: str,
    start_day: date,
    end_day: date,
) -> tuple[str, list[tuple[date, float]]]:
    totals: dict[date, float] = defaultdict(float)
    location_name = location_slug

    for row in rows:
        if row.location_slug != location_slug:
            continue
        if threat_type != "all" and row.threat_type != threat_type:
            continue
        location_name = row.location_name
        if start_day <= row.day <= end_day:
            totals[row.day] += row.active_hours

    series: list[tuple[date, float]] = []
    cursor = start_day
    while cursor <= end_day:
        series.append((cursor, totals.get(cursor, 0.0)))
        cursor += timedelta(days=1)
    return location_name, series


class AlertHoursApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Air Alert Hours")
        self.geometry("1180x720")
        self.minsize(900, 560)

        if not DATA_PATH.exists():
            messagebox.showerror("Dataset missing", f"Cannot find:\n{DATA_PATH}")
            raise SystemExit(1)

        self.rows = load_rows(DATA_PATH)
        self.min_day = min(row.day for row in self.rows)
        self.max_day = max(row.day for row in self.rows)
        self.location_choices, self.slug_by_choice = build_location_choices(self.rows)

        self.region_var = tk.StringVar(value=self._default_location_label())
        self.threat_var = tk.StringVar(value="air_raid")
        self.start_var = tk.StringVar(value=self.min_day.isoformat())
        self.end_var = tk.StringVar(value=self.max_day.isoformat())
        self.status_var = tk.StringVar()

        self._build_layout()
        self.draw_graph()

    def _default_location_label(self) -> str:
        for label, slug in self.slug_by_choice.items():
            if slug == DEFAULT_LOCATION_SLUG:
                return label
        return self.location_choices[0]

    def _build_layout(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Region").grid(row=0, column=0, sticky="w")
        region = ttk.Combobox(
            controls,
            textvariable=self.region_var,
            values=self.location_choices,
            state="readonly",
            width=58,
        )
        region.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(controls, text="Threat").grid(row=0, column=1, sticky="w")
        threat = ttk.Combobox(
            controls,
            textvariable=self.threat_var,
            values=("air_raid", "artillery_shelling", "all"),
            state="readonly",
            width=18,
        )
        threat.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(controls, text="Start date").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.start_var, width=14).grid(row=1, column=2, padx=(0, 10))

        ttk.Label(controls, text="End date").grid(row=0, column=3, sticky="w")
        ttk.Entry(controls, textvariable=self.end_var, width=14).grid(row=1, column=3, padx=(0, 10))

        ttk.Button(controls, text="Draw graph", command=self.draw_graph).grid(row=1, column=4, sticky="ew")
        controls.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, background="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self.draw_graph())

        status = ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 8))
        status.pack(fill=tk.X)

    def draw_graph(self) -> None:
        try:
            start_day = parse_day(self.start_var.get())
            end_day = parse_day(self.end_var.get())
            if start_day > end_day:
                raise ValueError("start date must be before end date")
        except ValueError as exc:
            self.status_var.set(f"Date error: {exc}. Use YYYY-MM-DD.")
            return

        location_slug = self.slug_by_choice.get(self.region_var.get())
        if not location_slug:
            self.status_var.set("Choose a region from the dropdown.")
            return

        location_name, series = make_series(
            self.rows,
            location_slug,
            self.threat_var.get(),
            start_day,
            end_day,
        )
        self._draw_series(location_name, series)

    def _draw_series(self, location_name: str, series: list[tuple[date, float]]) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 900)
        height = max(canvas.winfo_height(), 420)
        left, right, top, bottom = 80, 35, 70, 70
        plot_w = width - left - right
        plot_h = height - top - bottom

        values = [value for _, value in series]
        smooth = rolling_mean(values)
        max_y = 24.0
        if self.threat_var.get() == "all":
            max_y = max(24.0, max(values, default=0.0), max(smooth, default=0.0))

        total = sum(values)
        avg = total / len(values) if values else 0.0
        max_index = max(range(len(series)), key=lambda index: series[index][1]) if series else 0
        max_day, max_value = series[max_index] if series else (date.today(), 0.0)

        canvas.create_text(
            left,
            25,
            anchor="w",
            text=f"Daily alarm hours: {location_name}",
            font=("Segoe UI", 16, "bold"),
            fill="#202124",
        )
        canvas.create_text(
            left,
            50,
            anchor="w",
            text=f"{series[0][0].isoformat()} to {series[-1][0].isoformat()} | "
            f"total {total:.1f}h | avg/day {avg:.2f}h | max {max_value:.2f}h on {max_day.isoformat()}",
            font=("Segoe UI", 10),
            fill="#4f5b66",
        )

        for tick in range(0, 25, 6):
            y = top + plot_h - (tick / max_y * plot_h)
            canvas.create_line(left, y, left + plot_w, y, fill="#e0e4e8")
            canvas.create_text(left - 10, y, anchor="e", text=str(tick), fill="#5f6368", font=("Segoe UI", 9))

        canvas.create_line(left, top, left, top + plot_h, fill="#202124")
        canvas.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill="#202124")

        if len(series) <= 1:
            self.status_var.set("Not enough data for this selection.")
            return

        day_span = max(1, (series[-1][0] - series[0][0]).days)
        bar_step = plot_w / max(1, len(series))
        bar_width = max(1, min(6, bar_step * 0.8))

        def xy(day: date, value: float) -> tuple[float, float]:
            x = left + ((day - series[0][0]).days / day_span * plot_w)
            y = top + plot_h - (value / max_y * plot_h)
            return x, y

        for index, (day, value) in enumerate(series):
            if value <= 0:
                continue
            x = left + index * bar_step
            y = top + plot_h - (value / max_y * plot_h)
            canvas.create_rectangle(x, y, x + bar_width, top + plot_h, fill="#9ecae1", outline="")

        points: list[float] = []
        for (day, _value), avg_value in zip(series, smooth):
            x, y = xy(day, avg_value)
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(*points, fill="#d62728", width=2.5, smooth=True)

        for index in range(0, len(series), max(1, len(series) // 8)):
            day = series[index][0]
            x, _ = xy(day, 0)
            canvas.create_text(x, top + plot_h + 25, text=day.strftime("%Y-%m-%d"), angle=30, fill="#5f6368")

        canvas.create_text(left, height - 22, anchor="w", text="Blue bars: daily hours. Red line: 7-day average.", fill="#4f5b66")
        self.status_var.set(f"Loaded {len(self.rows):,} daily rows from {DATA_PATH}")


def main() -> None:
    AlertHoursApp().mainloop()


if __name__ == "__main__":
    main()
