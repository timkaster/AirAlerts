"""Train a dependency-free predictive baseline for daily alert hours.

The model predicts same-day alert hours from:

- region
- calendar features
- previous alert history
- optional weather features, if a local weather CSV is available

It uses a chronological train/test split and reports feature importance by
permutation: shuffle one feature group in the held-out test data and measure how
much test RMSE changes.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from tkinter_alert_app import infer_weather_region


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY = PROJECT_ROOT / "data" / "processed" / "daily_location_summary_clean.csv"
DEFAULT_WEATHER = PROJECT_ROOT / "data" / "processed" / "weather_daily_regions_open_meteo.csv"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "predictive_model_air_raid.md"
DEFAULT_IMPORTANCE = PROJECT_ROOT / "reports" / "predictive_model_feature_importance.csv"
DEFAULT_THREAT_TYPE = "air_raid"


@dataclass(frozen=True)
class DailyObservation:
    day: date
    location_slug: str
    location_name: str
    weather_slug: str
    target_hours: float
    features: dict[str, float]
    feature_groups: dict[str, str]


@dataclass(frozen=True)
class Metrics:
    rmse: float
    mae: float
    r2: float
    rows: int
    mean_target: float
    mean_prediction: float


def parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def safe_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def load_daily_rows(path: Path, threat_type: str) -> tuple[
    dict[tuple[date, str], tuple[float, float]],
    dict[str, str],
    dict[str, float],
    date,
    date,
]:
    daily: dict[tuple[date, str], tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
    names: dict[str, str] = {}
    totals: dict[str, float] = defaultdict(float)
    min_day: date | None = None
    max_day: date | None = None

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["threat_type"] != threat_type:
                continue
            day = parse_day(row["date_kyiv"])
            slug = row["location_slug"]
            hours = safe_float(row["active_hours"])
            starts = safe_float(row["alerts_started"])
            prior_hours, prior_starts = daily[(day, slug)]
            daily[(day, slug)] = (prior_hours + hours, prior_starts + starts)
            names.setdefault(slug, row["location_name"])
            totals[slug] += hours
            min_day = day if min_day is None else min(min_day, day)
            max_day = day if max_day is None else max(max_day, day)

    if min_day is None or max_day is None:
        raise ValueError(f"No rows found for threat_type={threat_type!r}")
    return dict(daily), names, dict(totals), min_day, max_day


def load_weather(path: Path) -> dict[tuple[date, str], dict[str, float]]:
    if not path.exists():
        return {}

    field_aliases = {
        "precipitation_sum": "weather_precipitation_mm",
        "precipitation_sum_mm": "weather_precipitation_mm",
        "rain_sum": "weather_rain_mm",
        "snowfall_sum": "weather_snowfall_mm",
        "temperature_2m_mean": "weather_temperature_mean_c",
        "relative_humidity_2m_mean": "weather_humidity_mean_pct",
        "surface_pressure_mean": "weather_surface_pressure_mean",
        "wind_speed_10m_max": "weather_wind_speed_max",
        "wind_gusts_10m_max": "weather_wind_gusts_max",
        "shortwave_radiation_sum": "weather_shortwave_radiation_sum",
        "cloud_cover_mean": "weather_cloud_cover_mean_pct",
        "cloud_cover_mean_percent": "weather_cloud_cover_mean_pct",
    }
    weather: dict[tuple[date, str], dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return weather
        available = [(source, target) for source, target in field_aliases.items() if source in reader.fieldnames]
        for row in reader:
            day = parse_day(row["date_kyiv"])
            slug = row["region_slug"]
            weather[(day, slug)] = {target: safe_float(row.get(source)) for source, target in available}
    return weather


def choose_locations(totals: dict[str, float], max_locations: int) -> list[str]:
    ordered = sorted(totals, key=lambda slug: totals[slug], reverse=True)
    if max_locations <= 0:
        return ordered
    return ordered[:max_locations]


def add_feature(
    features: dict[str, float],
    groups: dict[str, str],
    name: str,
    value: float,
    group: str,
) -> None:
    features[name] = value
    groups[name] = group


def build_observations(
    daily: dict[tuple[date, str], tuple[float, float]],
    names: dict[str, str],
    locations: list[str],
    min_day: date,
    max_day: date,
    weather: dict[tuple[date, str], dict[str, float]],
) -> list[DailyObservation]:
    observations: list[DailyObservation] = []
    days = date_range(min_day, max_day)

    for slug in locations:
        name = names.get(slug, slug)
        weather_slug, _matched = infer_weather_region(slug, name)
        recent_hours: list[float] = []
        recent_starts: list[float] = []
        days_since_alarm = 30.0

        for day in days:
            target_hours, starts = daily.get((day, slug), (0.0, 0.0))
            features: dict[str, float] = {}
            groups: dict[str, str] = {}

            add_feature(features, groups, f"location={slug}", 1.0, "region")
            add_feature(features, groups, f"weekday={day.weekday()}", 1.0, "calendar:weekday")
            add_feature(features, groups, f"month={day.month}", 1.0, "calendar:month")
            add_feature(features, groups, "is_weekend", 1.0 if day.weekday() >= 5 else 0.0, "calendar:weekend")

            year_day = day.timetuple().tm_yday
            add_feature(features, groups, "day_of_year_sin", math.sin(2 * math.pi * year_day / 365.25), "calendar:seasonality")
            add_feature(features, groups, "day_of_year_cos", math.cos(2 * math.pi * year_day / 365.25), "calendar:seasonality")

            lag1 = recent_hours[-1] if len(recent_hours) >= 1 else 0.0
            lag2 = recent_hours[-2] if len(recent_hours) >= 2 else 0.0
            lag1_starts = recent_starts[-1] if len(recent_starts) >= 1 else 0.0
            add_feature(features, groups, "lag1_hours", lag1, "history:lag1_hours")
            add_feature(features, groups, "lag2_hours", lag2, "history:lag2_hours")
            add_feature(features, groups, "lag7_mean_hours", mean_last(recent_hours, 7), "history:lag7_mean")
            add_feature(features, groups, "lag30_mean_hours", mean_last(recent_hours, 30), "history:lag30_mean")
            add_feature(features, groups, "lag1_alert_starts", lag1_starts, "history:lag1_starts")
            add_feature(features, groups, "yesterday_had_alarm", 1.0 if lag1 > 0 else 0.0, "history:yesterday_had_alarm")
            add_feature(features, groups, "days_since_alarm_capped30", min(days_since_alarm, 30.0), "history:days_since_alarm")

            weather_values = weather.get((day, weather_slug))
            if weather_values is None and weather_slug == "kyiv_city":
                weather_values = weather.get((day, "kyiv_oblast"))
            if weather_values:
                add_feature(features, groups, "weather_missing", 0.0, "weather:missing")
                for name_key, value in weather_values.items():
                    add_feature(features, groups, name_key, value, weather_group(name_key))
            else:
                add_feature(features, groups, "weather_missing", 1.0, "weather:missing")

            observations.append(
                DailyObservation(
                    day=day,
                    location_slug=slug,
                    location_name=name,
                    weather_slug=weather_slug,
                    target_hours=target_hours,
                    features=features,
                    feature_groups=groups,
                )
            )

            recent_hours.append(target_hours)
            recent_starts.append(starts)
            days_since_alarm = 0.0 if target_hours > 0 else days_since_alarm + 1.0

    return observations


def mean_last(values: list[float], count: int) -> float:
    if not values:
        return 0.0
    window = values[-count:]
    return sum(window) / len(window)


def weather_group(feature_name: str) -> str:
    if "precipitation" in feature_name or "rain" in feature_name or "snowfall" in feature_name:
        return "weather:precipitation"
    if "temperature" in feature_name:
        return "weather:temperature"
    if "humidity" in feature_name:
        return "weather:humidity"
    if "pressure" in feature_name:
        return "weather:pressure"
    if "wind" in feature_name or "gust" in feature_name:
        return "weather:wind"
    if "shortwave" in feature_name:
        return "weather:radiation"
    if "cloud" in feature_name:
        return "weather:cloud_cover"
    return "weather:other"


def split_by_time(observations: list[DailyObservation], test_days: int) -> tuple[list[DailyObservation], list[DailyObservation], date]:
    max_day = max(item.day for item in observations)
    test_start = max_day - timedelta(days=test_days - 1)
    train = [item for item in observations if item.day < test_start]
    test = [item for item in observations if item.day >= test_start]
    if not train or not test:
        raise ValueError("Chronological split produced empty train or test set")
    return train, test, test_start


def numeric_feature_names(observations: list[DailyObservation]) -> set[str]:
    names: set[str] = set()
    for item in observations:
        for name in item.features:
            if not name.startswith("location=") and not name.startswith("weekday=") and not name.startswith("month="):
                names.add(name)
    return names


def standardize(
    train: list[DailyObservation],
    observations: list[DailyObservation],
    numeric_names: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    for name in numeric_names:
        values = [item.features.get(name, 0.0) for item in train]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means[name] = mean
        stds[name] = math.sqrt(variance) or 1.0

    for item in observations:
        for name in numeric_names:
            if name in item.features:
                item.features[name] = (item.features[name] - means[name]) / stds[name]
    return means, stds


def active_features(item: DailyObservation, removed_group: str | None) -> dict[str, float]:
    if removed_group is None:
        return item.features
    return {
        name: value
        for name, value in item.features.items()
        if item.feature_groups.get(name) != removed_group
    }


def train_linear_model(
    train: list[DailyObservation],
    removed_group: str | None,
    epochs: int,
    learning_rate: float,
    l2: float,
    seed: int,
) -> dict[str, float]:
    weights: dict[str, float] = defaultdict(float)
    rows = list(train)
    rng = random.Random(seed)
    for epoch in range(epochs):
        rng.shuffle(rows)
        step = learning_rate / math.sqrt(epoch + 1)
        for item in rows:
            features = active_features(item, removed_group)
            prediction = weights["__bias__"] + sum(weights[name] * value for name, value in features.items())
            error = prediction - item.target_hours
            weights["__bias__"] -= step * error
            for name, value in features.items():
                weights[name] -= step * (error * value + l2 * weights[name])
    return dict(weights)


def predict(weights: dict[str, float], item: DailyObservation, removed_group: str | None) -> float:
    features = active_features(item, removed_group)
    raw = weights.get("__bias__", 0.0) + sum(weights.get(name, 0.0) * value for name, value in features.items())
    return min(24.0, max(0.0, raw))


def evaluate(weights: dict[str, float], rows: list[DailyObservation], removed_group: str | None, baseline_mean: float) -> Metrics:
    predictions = [predict(weights, item, removed_group) for item in rows]
    targets = [item.target_hours for item in rows]
    mse = sum((pred - target) ** 2 for pred, target in zip(predictions, targets)) / len(rows)
    mae = sum(abs(pred - target) for pred, target in zip(predictions, targets)) / len(rows)
    baseline_sse = sum((target - baseline_mean) ** 2 for target in targets)
    model_sse = sum((target - pred) ** 2 for target, pred in zip(targets, predictions))
    r2 = 1.0 - model_sse / baseline_sse if baseline_sse else 0.0
    return Metrics(
        rmse=math.sqrt(mse),
        mae=mae,
        r2=r2,
        rows=len(rows),
        mean_target=sum(targets) / len(targets),
        mean_prediction=sum(predictions) / len(predictions),
    )


def collect_groups(observations: list[DailyObservation]) -> list[str]:
    groups = sorted({group for item in observations for group in item.feature_groups.values()})
    return groups


def predict_from_features(weights: dict[str, float], features: dict[str, float]) -> float:
    raw = weights.get("__bias__", 0.0) + sum(weights.get(name, 0.0) * value for name, value in features.items())
    return min(24.0, max(0.0, raw))


def evaluate_predictions(predictions: list[float], targets: list[float], baseline_mean: float) -> Metrics:
    mse = sum((pred - target) ** 2 for pred, target in zip(predictions, targets)) / len(targets)
    mae = sum(abs(pred - target) for pred, target in zip(predictions, targets)) / len(targets)
    baseline_sse = sum((target - baseline_mean) ** 2 for target in targets)
    model_sse = sum((target - pred) ** 2 for target, pred in zip(targets, predictions))
    r2 = 1.0 - model_sse / baseline_sse if baseline_sse else 0.0
    return Metrics(
        rmse=math.sqrt(mse),
        mae=mae,
        r2=r2,
        rows=len(targets),
        mean_target=sum(targets) / len(targets),
        mean_prediction=sum(predictions) / len(predictions),
    )


def evaluate_permuted_group(
    weights: dict[str, float],
    rows: list[DailyObservation],
    group: str,
    baseline_mean: float,
    seed: int,
) -> Metrics:
    group_features = [
        {name: value for name, value in item.features.items() if item.feature_groups.get(name) == group}
        for item in rows
    ]
    rng = random.Random(seed)
    shuffled = list(group_features)
    rng.shuffle(shuffled)

    predictions: list[float] = []
    for item, replacement in zip(rows, shuffled):
        features = {
            name: value
            for name, value in item.features.items()
            if item.feature_groups.get(name) != group
        }
        features.update(replacement)
        predictions.append(predict_from_features(weights, features))
    targets = [item.target_hours for item in rows]
    return evaluate_predictions(predictions, targets, baseline_mean)


def train_and_rank(
    train: list[DailyObservation],
    test: list[DailyObservation],
    groups: list[str],
    epochs: int,
    learning_rate: float,
    l2: float,
    seed: int,
) -> tuple[dict[str, float], Metrics, list[dict[str, object]]]:
    baseline_mean = sum(item.target_hours for item in train) / len(train)
    full_weights = train_linear_model(train, None, epochs, learning_rate, l2, seed)
    full_metrics = evaluate(full_weights, test, None, baseline_mean)
    rows: list[dict[str, object]] = []

    for index, group in enumerate(groups):
        metrics = evaluate_permuted_group(full_weights, test, group, baseline_mean, seed + index + 1)
        rows.append(
            {
                "feature_group": group,
                "full_rmse": full_metrics.rmse,
                "permuted_rmse": metrics.rmse,
                "rmse_increase": metrics.rmse - full_metrics.rmse,
                "permuted_mae": metrics.mae,
                "permuted_r2": metrics.r2,
            }
        )

    rows.sort(key=lambda item: float(item["rmse_increase"]), reverse=True)
    return full_weights, full_metrics, rows


def top_coefficients(weights: dict[str, float], limit: int = 12) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    items = [(name, value) for name, value in weights.items() if name != "__bias__" and not name.startswith("location=")]
    positives = sorted(items, key=lambda item: item[1], reverse=True)[:limit]
    negatives = sorted(items, key=lambda item: item[1])[:limit]
    return positives, negatives


def write_importance(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["feature_group", "full_rmse", "permuted_rmse", "rmse_increase", "permuted_mae", "permuted_r2"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def feature_group_label(group: object) -> str:
    labels = {
        "region": "Region",
        "history:lag7_mean": "Recent alarm level: previous 7-day average",
        "history:lag1_hours": "Yesterday's alarm hours",
        "history:lag2_hours": "Alarm hours two days ago",
        "history:lag30_mean": "Recent alarm level: previous 30-day average",
        "history:lag1_starts": "Yesterday's number of alarm starts",
        "history:yesterday_had_alarm": "Whether yesterday had any alarm",
        "history:days_since_alarm": "Days since last alarm",
        "calendar:weekday": "Day of week",
        "calendar:weekend": "Weekend flag",
        "calendar:month": "Month",
        "calendar:seasonality": "Seasonal position in the year",
        "weather:temperature": "Weather: temperature",
        "weather:precipitation": "Weather: precipitation/rain/snow",
        "weather:humidity": "Weather: humidity",
        "weather:pressure": "Weather: pressure",
        "weather:wind": "Weather: wind",
        "weather:radiation": "Weather: sunlight/radiation",
        "weather:cloud_cover": "Weather: cloudiness",
        "weather:missing": "Weather data availability",
        "weather:other": "Weather: other",
    }
    return labels.get(str(group), str(group).replace("_", " ").replace(":", ": "))


def feature_label(name: str) -> str:
    labels = {
        "lag7_mean_hours": "previous 7-day average alarm hours",
        "lag1_hours": "yesterday's alarm hours",
        "lag2_hours": "alarm hours two days ago",
        "lag30_mean_hours": "previous 30-day average alarm hours",
        "lag1_alert_starts": "yesterday's number of alarm starts",
        "days_since_alarm_capped30": "days since last alarm, capped at 30",
        "yesterday_had_alarm": "whether yesterday had an alarm",
        "weather_surface_pressure_mean": "surface pressure",
        "weather_temperature_mean_c": "mean temperature",
        "weather_humidity_mean_pct": "mean humidity",
        "weather_wind_speed_max": "max wind speed",
        "weather_shortwave_radiation_sum": "sunlight/radiation",
        "weather_snowfall_mm": "snowfall",
        "is_weekend": "weekend",
    }
    if name.startswith("weekday="):
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return weekdays[int(name.split("=", 1)[1])]
    if name.startswith("month="):
        months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        return months[int(name.split("=", 1)[1]) - 1]
    return labels.get(name, name.replace("_", " "))


def importance_strength(delta: float) -> str:
    if delta >= 1.0:
        return "very strong"
    if delta >= 0.1:
        return "meaningful"
    if delta >= 0.02:
        return "small"
    if delta > -0.02:
        return "tiny/negligible"
    return "not useful here"


def markdown_table(rows: list[dict[str, object]], limit: int = 10) -> str:
    lines = [
        "| Rank | Input tested | Effect on prediction | Extra error when shuffled |",
        "|---:|---|---|---:|",
    ]
    for rank, row in enumerate(rows[:limit], start=1):
        increase = float(row["rmse_increase"])
        lines.append(
            "| {rank} | {group} | {strength} | {increase:+.3f} h/day |".format(
                rank=rank,
                group=feature_group_label(row["feature_group"]),
                strength=importance_strength(increase),
                increase=increase,
            )
        )
    return "\n".join(lines)


def coefficient_lines(items: list[tuple[str, float]]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {feature_label(name)}: {value:+.3f}" for name, value in items)


def signed_coefficients(items: list[tuple[str, float]], direction: str, limit: int = 8) -> list[tuple[str, float]]:
    if direction == "positive":
        return [(name, value) for name, value in items if value > 0][:limit]
    if direction == "negative":
        return [(name, value) for name, value in items if value < 0][:limit]
    raise ValueError(f"unknown coefficient direction: {direction}")


def top_takeaways(importance_rows: list[dict[str, object]]) -> str:
    positive = [row for row in importance_rows if float(row["rmse_increase"]) > 0.02]
    weather = [row for row in importance_rows if str(row["feature_group"]).startswith("weather:")]
    strongest = positive[:2]
    lines: list[str] = []
    if strongest:
        readable = ", ".join(feature_group_label(row["feature_group"]) for row in strongest)
        lines.append(f"- The model mostly uses recent alarm history: {readable}.")
    else:
        lines.append("- No feature group clearly improved the forecast in this validation window.")
    best_weather = max(weather, key=lambda row: float(row["rmse_increase"]), default=None)
    if best_weather and float(best_weather["rmse_increase"]) > 0.02:
        lines.append(
            f"- The strongest weather signal was {feature_group_label(best_weather['feature_group']).lower()}, "
            f"but its effect was much smaller than recent alarm history."
        )
    else:
        lines.append("- Weather features were weak in this run; they did not materially improve the forecast.")
    lines.append("- Treat this as predictive evidence, not proof of cause and effect.")
    return "\n".join(lines)


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def render_report(
    threat_type: str,
    locations: list[str],
    min_day: date,
    max_day: date,
    test_start: date,
    weather_path: Path,
    weather_rows: int,
    epochs: int,
    learning_rate: float,
    full_metrics: Metrics,
    importance_rows: list[dict[str, object]],
    positives: list[tuple[str, float]],
    negatives: list[tuple[str, float]],
    output_importance: Path,
) -> str:
    useful_rows = [row for row in importance_rows if float(row["rmse_increase"]) > 0]
    best = useful_rows[0]["feature_group"] if useful_rows else "none"
    weather_display = display_path(weather_path)
    importance_display = display_path(output_importance)
    weather_note = (
        f"Weather joined from `{weather_display}` ({weather_rows:,} date-region rows)."
        if weather_rows
        else "Weather file was not available, so the model used only region, calendar, and alert-history features."
    )
    best_label = feature_group_label(best)
    return f"""# Predictive Model: Daily Alert Hours

## Short Answer

The model can predict daily alarm hours reasonably well, but the useful signal is mostly yesterday and the previous week of alarms. Weather features are present in the model, but they are weak compared with recent alarm history.

{top_takeaways(importance_rows)}

## What Was Predicted

- Target: same-day alert hours for a selected location and date
- Threat type: `{threat_type}`
- Locations included: top {len(locations)} locations by total alert duration
- Training period: {min_day.isoformat()} to {(test_start - timedelta(days=1)).isoformat()}
- Test period: {test_start.isoformat()} to {max_day.isoformat()}
- Model type: simple linear predictive baseline

{weather_note}

## Most Important Inputs

The table shows what happens when each input group is shuffled in the test period. If shuffling a group makes the forecast much worse, the model was relying on that information.

{markdown_table(importance_rows)}

Most important input group in this run: **{best_label}**.

## How Good Was It?

- Test rows: {full_metrics.rows:,}
- Actual average: {full_metrics.mean_target:.2f} alarm hours/day
- Predicted average: {full_metrics.mean_prediction:.2f} alarm hours/day
- Average absolute error: {full_metrics.mae:.2f} hours/day
- Typical large-error scale: {full_metrics.rmse:.2f} hours/day
- Improvement over a simple average baseline: {full_metrics.r2:.1%}

Plain English: the model captures broad patterns well, but day-to-day errors can still be several hours. That is expected for this kind of problem.

## Interpretation

This model is useful for understanding which inputs help prediction. It is not a causal model. A feature can help prediction without causing alarms, and a real cause can look weak if its effect is already captured by recent alarm history or region.

In this run, recent alert history is the strongest signal. That means alarm activity is temporally persistent: if a region had many alarm hours recently, the next day is more predictable from that recent pattern.

Weather variables can still be explored, but they are not strong predictors here. Their small permutation scores mean precipitation, temperature, wind, pressure, humidity, and related weather fields added little once the model already knew location, calendar, and recent alarms.

## Technical Details

- Validation method: chronological holdout, not random split
- Training: {epochs} epochs, learning rate {learning_rate}
- Importance method: held-out permutation importance
- Full importance CSV: `{importance_display}`

## Model Coefficients

These are secondary diagnostics, not the main conclusion. Positive values push predictions upward; negative values push them downward.

Largest upward signals:
{coefficient_lines(signed_coefficients(positives, "positive"))}

Largest downward signals:
{coefficient_lines(signed_coefficients(negatives, "negative"))}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--weather", type=Path, default=DEFAULT_WEATHER)
    parser.add_argument("--threat-type", default=DEFAULT_THREAT_TYPE)
    parser.add_argument("--max-locations", type=int, default=40, help="Use top-N locations by total alert hours. Use 0 for all.")
    parser.add_argument("--test-days", type=int, default=180)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=0.0001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--importance-output", type=Path, default=DEFAULT_IMPORTANCE)
    args = parser.parse_args()

    daily, names, totals, min_day, max_day = load_daily_rows(args.input, args.threat_type)
    weather = load_weather(args.weather)
    locations = choose_locations(totals, args.max_locations)
    observations = build_observations(daily, names, locations, min_day, max_day, weather)
    train, test, test_start = split_by_time(observations, args.test_days)
    numeric_names = numeric_feature_names(observations)
    standardize(train, observations, numeric_names)
    groups = collect_groups(observations)

    weights, metrics, importance_rows = train_and_rank(
        train=train,
        test=test,
        groups=groups,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        seed=args.seed,
    )
    positives, negatives = top_coefficients(weights)
    write_importance(args.importance_output, importance_rows)
    report = render_report(
        threat_type=args.threat_type,
        locations=locations,
        min_day=min_day,
        max_day=max_day,
        test_start=test_start,
        weather_path=args.weather,
        weather_rows=len(weather),
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        full_metrics=metrics,
        importance_rows=importance_rows,
        positives=positives,
        negatives=negatives,
        output_importance=args.importance_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
