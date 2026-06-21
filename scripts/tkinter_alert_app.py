"""Tkinter app for comparing daily alert hours with precipitation and cloudiness.

Run from PyCharm with the project interpreter:

    python scripts/tkinter_alert_app.py

The app uses only the Python standard library.
"""

from __future__ import annotations

import csv
import math
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from fetch_open_meteo_weather import REGION_POINTS, build_rows, request_precipitation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "daily_location_summary_clean.csv"
DEFAULT_LOCATION_SLUG = "\u043c_\u041a\u0438\u0457\u0432"
DEFAULT_WEATHER_REGION = "kyiv_city"

ALERT_TO_WEATHER_REGION = {
    "\u043c_\u041a\u0438\u0457\u0432": "kyiv_city",
    "\u041a\u0438\u0457\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "kyiv_oblast",
    "\u0412\u0456\u043d\u043d\u0438\u0446\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "vinnytsia_oblast",
    "\u0412\u043e\u043b\u0438\u043d\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "volyn_oblast",
    "\u0414\u043d\u0456\u043f\u0440\u043e\u043f\u0435\u0442\u0440\u043e\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "dnipropetrovsk_oblast",
    "\u0414\u043e\u043d\u0435\u0446\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "donetsk_oblast",
    "\u0416\u0438\u0442\u043e\u043c\u0438\u0440\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "zhytomyr_oblast",
    "\u0417\u0430\u043a\u0430\u0440\u043f\u0430\u0442\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "zakarpattia_oblast",
    "\u0417\u0430\u043f\u043e\u0440\u0456\u0437\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "zaporizhzhia_oblast",
    "\u0406\u0432\u0430\u043d\u043e\u0424\u0440\u0430\u043d\u043a\u0456\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "ivano_frankivsk_oblast",
    "\u041a\u0456\u0440\u043e\u0432\u043e\u0433\u0440\u0430\u0434\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "kirovohrad_oblast",
    "\u041b\u0443\u0433\u0430\u043d\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "luhansk_oblast",
    "\u041b\u044c\u0432\u0456\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "lviv_oblast",
    "\u041c\u0438\u043a\u043e\u043b\u0430\u0457\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "mykolaiv_oblast",
    "\u041e\u0434\u0435\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "odesa_oblast",
    "\u041f\u043e\u043b\u0442\u0430\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "poltava_oblast",
    "\u0420\u0456\u0432\u043d\u0435\u043d\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "rivne_oblast",
    "\u0421\u0443\u043c\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "sumy_oblast",
    "\u0422\u0435\u0440\u043d\u043e\u043f\u0456\u043b\u044c\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "ternopil_oblast",
    "\u0425\u0430\u0440\u043a\u0456\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "kharkiv_oblast",
    "\u0425\u0435\u0440\u0441\u043e\u043d\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "kherson_oblast",
    "\u0425\u043c\u0435\u043b\u044c\u043d\u0438\u0446\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "khmelnytskyi_oblast",
    "\u0427\u0435\u0440\u043a\u0430\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "cherkasy_oblast",
    "\u0427\u0435\u0440\u043d\u0456\u0432\u0435\u0446\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "chernivtsi_oblast",
    "\u0427\u0435\u0440\u043d\u0456\u0433\u0456\u0432\u0441\u044c\u043a\u0430_\u043e\u0431\u043b\u0430\u0441\u0442\u044c": "chernihiv_oblast",
}

WEATHER_CLUES = [
    ("\u043a\u0438\u0457\u0432", "kyiv_city"),
    ("\u0445\u0430\u0440\u043a\u0456\u0432", "kharkiv_oblast"),
    ("\u0437\u0430\u043f\u043e\u0440\u0456\u0436", "zaporizhzhia_oblast"),
    ("\u0437\u0430\u043f\u043e\u0440\u0456\u0437", "zaporizhzhia_oblast"),
    ("\u0434\u043d\u0456\u043f\u0440", "dnipropetrovsk_oblast"),
    ("\u043d\u0456\u043a\u043e\u043f\u043e\u043b", "dnipropetrovsk_oblast"),
    ("\u043a\u0440\u0438\u0432", "dnipropetrovsk_oblast"),
    ("\u043e\u0434\u0435\u0441", "odesa_oblast"),
    ("\u043c\u0438\u043a\u043e\u043b\u0430", "mykolaiv_oblast"),
    ("\u0445\u0435\u0440\u0441\u043e\u043d", "kherson_oblast"),
    ("\u0441\u0443\u043c", "sumy_oblast"),
    ("\u043f\u043e\u043b\u0442\u0430\u0432", "poltava_oblast"),
    ("\u0447\u0435\u0440\u043d\u0456\u0433", "chernihiv_oblast"),
    ("\u0447\u0435\u0440\u043a\u0430\u0441", "cherkasy_oblast"),
    ("\u0436\u0438\u0442\u043e\u043c\u0438\u0440", "zhytomyr_oblast"),
    ("\u0432\u0456\u043d\u043d\u0438\u0446", "vinnytsia_oblast"),
    ("\u0445\u043c\u0435\u043b\u044c\u043d", "khmelnytskyi_oblast"),
    ("\u0442\u0435\u0440\u043d\u043e\u043f", "ternopil_oblast"),
    ("\u043b\u044c\u0432\u0456\u0432", "lviv_oblast"),
    ("\u0456\u0432\u0430\u043d\u043e", "ivano_frankivsk_oblast"),
    ("\u0440\u0456\u0432\u043d", "rivne_oblast"),
    ("\u0432\u043e\u043b\u0438\u043d", "volyn_oblast"),
    ("\u0443\u0436\u0433\u043e\u0440", "zakarpattia_oblast"),
    ("\u0437\u0430\u043a\u0430\u0440\u043f", "zakarpattia_oblast"),
    ("\u0434\u043e\u043d\u0435\u0446", "donetsk_oblast"),
    ("\u043b\u0443\u0433\u0430\u043d", "luhansk_oblast"),
    ("\u043a\u0440\u0438\u043c", "crimea"),
]

REGION_BY_SLUG = {region.region_slug: region for region in REGION_POINTS}

UKRAINIAN_LATIN = str.maketrans(
    {
        "\u0430": "a",
        "\u0431": "b",
        "\u0432": "v",
        "\u0433": "h",
        "\u0491": "g",
        "\u0434": "d",
        "\u0435": "e",
        "\u0454": "ie",
        "\u0436": "zh",
        "\u0437": "z",
        "\u0438": "y",
        "\u0456": "i",
        "\u0457": "i",
        "\u0439": "i",
        "\u043a": "k",
        "\u043b": "l",
        "\u043c": "m",
        "\u043d": "n",
        "\u043e": "o",
        "\u043f": "p",
        "\u0440": "r",
        "\u0441": "s",
        "\u0442": "t",
        "\u0443": "u",
        "\u0444": "f",
        "\u0445": "kh",
        "\u0446": "ts",
        "\u0447": "ch",
        "\u0448": "sh",
        "\u0449": "shch",
        "\u044c": "",
        "\u044e": "iu",
        "\u044f": "ia",
        "\u2019": "",
        "'": "",
    }
)


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


def transliterate_ukrainian(value: str) -> str:
    return value.casefold().translate(UKRAINIAN_LATIN)


def filter_location_choices(choices: list[str], query: str) -> list[str]:
    words = transliterate_ukrainian(query.replace("_", " ")).split()
    if not words:
        return choices
    matches: list[str] = []
    for choice in choices:
        searchable = f"{choice} {transliterate_ukrainian(choice)}".replace("_", " ").casefold()
        if all(word in searchable for word in words):
            matches.append(choice)
    return matches


def infer_weather_region(location_slug: str, location_name: str) -> tuple[str, bool]:
    exact = ALERT_TO_WEATHER_REGION.get(location_slug)
    if exact:
        return exact, True

    text = f"{location_slug} {location_name}".replace("_", " ").casefold()
    for clue, weather_slug in WEATHER_CLUES:
        if clue in text:
            return weather_slug, True

    return DEFAULT_WEATHER_REGION, False


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


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def conclusion_text(
    alert_series: list[tuple[date, float]],
    precip_series: list[tuple[date, float]],
    cloud_series: list[tuple[date, float]],
) -> str:
    precip_by_day = dict(precip_series)
    cloud_by_day = dict(cloud_series)
    pairs = [(alert_hours, precip_by_day.get(day, 0.0)) for day, alert_hours in alert_series]
    wet_alerts = [alert for alert, precip in pairs if precip > 0]
    dry_alerts = [alert for alert, precip in pairs if precip <= 0]
    wet_avg = sum(wet_alerts) / len(wet_alerts) if wet_alerts else 0.0
    dry_avg = sum(dry_alerts) / len(dry_alerts) if dry_alerts else 0.0
    corr = pearson([alert for alert, _ in pairs], [precip for _, precip in pairs])
    cloud_pairs = [(alert_hours, cloud_by_day.get(day, 0.0)) for day, alert_hours in alert_series]
    cloud_corr = pearson([alert for alert, _ in cloud_pairs], [cloud for _, cloud in cloud_pairs])
    corr_text = "not defined" if corr is None else f"{corr:.2f}"
    cloud_corr_text = "not defined" if cloud_corr is None else f"{cloud_corr:.2f}"
    if corr is None:
        relationship = "not enough variation to estimate correlation"
    elif abs(corr) < 0.2:
        relationship = "little linear relationship"
    elif corr > 0:
        relationship = "alerts were somewhat higher on wetter days"
    else:
        relationship = "alerts were somewhat lower on wetter days"
    return (
        f"Conclusion: wet days averaged {wet_avg:.2f} alarm h/day ({len(wet_alerts)} days), "
        f"dry days averaged {dry_avg:.2f} h/day ({len(dry_alerts)} days); "
        f"precipitation/alarm r={corr_text}, {relationship}; cloudiness/alarm r={cloud_corr_text}."
    )


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
        self.weather_cache: dict[tuple[str, date, date], tuple[list[tuple[date, float]], list[tuple[date, float]]]] = {}
        self.filtered_location_choices = list(self.location_choices)

        self.search_var = tk.StringVar()
        self.region_var = tk.StringVar(value=self._default_location_label())
        self.threat_var = tk.StringVar(value="air_raid")
        default_start = max(self.min_day, self.max_day - timedelta(days=29))
        self.start_var = tk.StringVar(value=default_start.isoformat())
        self.end_var = tk.StringVar(value=self.max_day.isoformat())
        self.status_var = tk.StringVar()

        self._build_layout()
        self.search_var.trace_add("write", self._on_search_changed)
        self.draw_graph()

    def _default_location_label(self) -> str:
        for label, slug in self.slug_by_choice.items():
            if slug == DEFAULT_LOCATION_SLUG:
                return label
        return self.location_choices[0]

    def _build_layout(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Search region").grid(row=0, column=0, sticky="w")
        search = ttk.Entry(controls, textvariable=self.search_var, width=26)
        search.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        search.bind("<Return>", self._select_first_search_match)

        ttk.Label(controls, text="Alarm region").grid(row=0, column=1, sticky="w")
        self.region_combo = ttk.Combobox(
            controls,
            textvariable=self.region_var,
            values=self.filtered_location_choices,
            state="readonly",
            width=68,
        )
        self.region_combo.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(controls, text="Threat").grid(row=0, column=2, sticky="w")
        threat = ttk.Combobox(
            controls,
            textvariable=self.threat_var,
            values=("air_raid", "artillery_shelling", "all"),
            state="readonly",
            width=18,
        )
        threat.grid(row=1, column=2, sticky="ew", padx=(0, 10))

        ttk.Label(controls, text="Start date").grid(row=0, column=3, sticky="w")
        ttk.Entry(controls, textvariable=self.start_var, width=14).grid(row=1, column=3, padx=(0, 10))

        ttk.Label(controls, text="End date").grid(row=0, column=4, sticky="w")
        ttk.Entry(controls, textvariable=self.end_var, width=14).grid(row=1, column=4, padx=(0, 10))

        ttk.Button(controls, text="Draw graph", command=self.draw_graph).grid(row=1, column=5, sticky="ew")
        controls.columnconfigure(1, weight=1)

        self.canvas = tk.Canvas(self, background="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self.draw_graph())

        status = ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 8))
        status.pack(fill=tk.X)

    def _on_search_changed(self, *_args: object) -> None:
        self.filtered_location_choices = filter_location_choices(self.location_choices, self.search_var.get())
        self.region_combo.configure(values=self.filtered_location_choices)
        if not self.filtered_location_choices:
            self.status_var.set("No alarm regions match the search.")
            return
        if self.region_var.get() not in self.filtered_location_choices:
            self.region_var.set(self.filtered_location_choices[0])
        self.status_var.set(f"{len(self.filtered_location_choices)} matching alarm regions.")

    def _select_first_search_match(self, _event: tk.Event) -> None:
        if self.filtered_location_choices:
            self.region_var.set(self.filtered_location_choices[0])
            self.draw_graph()

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
            self.status_var.set("Choose an alarm region from the dropdown.")
            return

        location_name, series = make_series(self.rows, location_slug, self.threat_var.get(), start_day, end_day)
        weather_slug, matched = infer_weather_region(location_slug, location_name)
        try:
            precip_series, cloud_series = self._get_weather_series(weather_slug, start_day, end_day)
        except Exception as exc:
            self.status_var.set(f"Could not fetch weather data: {exc}")
            return
        self._draw_combined(location_name, weather_slug, matched, series, precip_series, cloud_series)

    def _get_weather_series(
        self, weather_slug: str, start_day: date, end_day: date
    ) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
        cache_key = (weather_slug, start_day, end_day)
        if cache_key in self.weather_cache:
            return self.weather_cache[cache_key]
        region = REGION_BY_SLUG[weather_slug]
        payload = request_precipitation(region, start_day, end_day)
        rows = build_rows(region, payload)
        precip_series = [(parse_day(str(row["date_kyiv"])), float(row["precipitation_sum_mm"] or 0.0)) for row in rows]
        cloud_series = [
            (parse_day(str(row["date_kyiv"])), float(row["cloud_cover_mean_percent"] or 0.0)) for row in rows
        ]
        self.weather_cache[cache_key] = (precip_series, cloud_series)
        return precip_series, cloud_series

    def _draw_combined(
        self,
        location_name: str,
        weather_slug: str,
        weather_matched: bool,
        alert_series: list[tuple[date, float]],
        precip_series: list[tuple[date, float]],
        cloud_series: list[tuple[date, float]],
    ) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 900)
        height = max(canvas.winfo_height(), 520)
        left, right, top, bottom = 80, 35, 86, 118
        plot_w = width - left - right
        gap = 46
        alert_h = int((height - top - bottom - gap) * 0.58)
        precip_h = height - top - bottom - gap - alert_h
        precip_top = top + alert_h + gap

        values = [value for _, value in alert_series]
        smooth = rolling_mean(values)
        max_y = 24.0
        if self.threat_var.get() == "all":
            max_y = max(24.0, max(values, default=0.0), max(smooth, default=0.0))
        precip_values = [value for _, value in precip_series]
        max_precip = max(1.0, max(precip_values, default=0.0))

        total = sum(values)
        avg = total / len(values) if values else 0.0
        max_index = max(range(len(alert_series)), key=lambda index: alert_series[index][1]) if alert_series else 0
        max_day, max_value = alert_series[max_index] if alert_series else (date.today(), 0.0)

        weather_region = REGION_BY_SLUG[weather_slug]
        match_note = "auto-matched" if weather_matched else "fallback proxy"

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
            text=f"{alert_series[0][0].isoformat()} to {alert_series[-1][0].isoformat()} | "
            f"total {total:.1f}h | avg/day {avg:.2f}h | max {max_value:.2f}h on {max_day.isoformat()}",
            font=("Segoe UI", 10),
            fill="#4f5b66",
        )
        canvas.create_text(
            left,
            70,
            anchor="w",
            text=f"Weather proxy: {weather_region.region_name_en} ({weather_region.representative_place}), {match_note}; weather from Open-Meteo.",
            font=("Segoe UI", 9),
            fill="#4f5b66",
        )

        for tick in range(0, 25, 6):
            y = top + alert_h - (tick / max_y * alert_h)
            canvas.create_line(left, y, left + plot_w, y, fill="#e0e4e8")
            canvas.create_text(left - 10, y, anchor="e", text=str(tick), fill="#5f6368", font=("Segoe UI", 9))

        canvas.create_line(left, top, left, top + alert_h, fill="#202124")
        canvas.create_line(left, top + alert_h, left + plot_w, top + alert_h, fill="#202124")
        canvas.create_text(24, top + alert_h / 2, text="Alarm hours", angle=90, fill="#202124")

        if len(alert_series) <= 1:
            self.status_var.set("Not enough data for this selection.")
            return

        day_span = max(1, (alert_series[-1][0] - alert_series[0][0]).days)
        bar_step = plot_w / max(1, len(alert_series))
        bar_width = max(1, min(6, bar_step * 0.8))

        def alert_xy(day: date, value: float) -> tuple[float, float]:
            x = left + ((day - alert_series[0][0]).days / day_span * plot_w)
            y = top + alert_h - (value / max_y * alert_h)
            return x, y

        def precip_y(value: float) -> float:
            return precip_top + precip_h - (value / max_precip * precip_h)

        def cloud_y(value: float) -> float:
            return precip_top + precip_h - (min(100.0, max(0.0, value)) / 100.0 * precip_h)

        for index, (_day, value) in enumerate(alert_series):
            if value <= 0:
                continue
            x = left + index * bar_step
            y = top + alert_h - (value / max_y * alert_h)
            canvas.create_rectangle(x, y, x + bar_width, top + alert_h, fill="#9ecae1", outline="")

        points: list[float] = []
        for (day, _value), avg_value in zip(alert_series, smooth):
            x, y = alert_xy(day, avg_value)
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(*points, fill="#d62728", width=2.5, smooth=True)

        for tick in range(0, 5):
            value = max_precip * tick / 4
            y = precip_y(value)
            canvas.create_line(left, y, left + plot_w, y, fill="#e0e4e8")
            canvas.create_text(left - 10, y, anchor="e", text=f"{value:.1f}", fill="#5f6368", font=("Segoe UI", 9))

        canvas.create_line(left, precip_top, left, precip_top + precip_h, fill="#202124")
        canvas.create_line(left, precip_top + precip_h, left + plot_w, precip_top + precip_h, fill="#202124")
        canvas.create_text(24, precip_top + precip_h / 2, text="Precip mm", angle=90, fill="#202124")
        canvas.create_line(left + plot_w, precip_top, left + plot_w, precip_top + precip_h, fill="#202124")
        for tick in range(0, 101, 25):
            y = cloud_y(float(tick))
            canvas.create_text(left + plot_w + 10, y, anchor="w", text=str(tick), fill="#5f6368", font=("Segoe UI", 9))
        canvas.create_text(width - 18, precip_top + precip_h / 2, text="Cloud %", angle=90, fill="#202124")

        precip_by_day = dict(precip_series)
        for index, (day, _alert_value) in enumerate(alert_series):
            value = precip_by_day.get(day, 0.0)
            if value <= 0:
                continue
            x = left + index * bar_step
            y = precip_y(value)
            canvas.create_rectangle(x, y, x + bar_width, precip_top + precip_h, fill="#74c476", outline="")

        cloud_by_day = dict(cloud_series)
        cloud_points: list[float] = []
        for day, _alert_value in alert_series:
            x, _ = alert_xy(day, 0)
            cloud_points.extend([x, cloud_y(cloud_by_day.get(day, 0.0))])
        if len(cloud_points) >= 4:
            canvas.create_line(*cloud_points, fill="#7b4ab8", width=2.2, smooth=True)

        for index in range(0, len(alert_series), max(1, len(alert_series) // 8)):
            day = alert_series[index][0]
            x, _ = alert_xy(day, 0)
            canvas.create_text(x, precip_top + precip_h + 25, text=day.strftime("%Y-%m-%d"), angle=30, fill="#5f6368")

        conclusion = conclusion_text(alert_series, precip_series, cloud_series)
        canvas.create_text(
            left,
            height - 58,
            anchor="w",
            text="Blue bars: alarm hours. Red line: 7-day alarm average. Green bars: precipitation. Purple line: mean cloud cover.",
            fill="#4f5b66",
            width=plot_w,
        )
        canvas.create_text(
            left,
            height - 40,
            anchor="nw",
            text=conclusion,
            fill="#202124",
            font=("Segoe UI", 10, "bold"),
            width=plot_w,
        )
        self.status_var.set(f"Loaded {len(self.rows):,} daily alert rows. Fetched weather data for {weather_slug}.")


def main() -> None:
    AlertHoursApp().mainloop()


if __name__ == "__main__":
    main()
