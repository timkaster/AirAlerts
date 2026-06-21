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


def markdown_table(rows: list[dict[str, object]], limit: int = 12) -> str:
    lines = ["| Rank | Feature group | RMSE increase when shuffled | Shuffled RMSE | Shuffled R2 |", "|---:|---|---:|---:|---:|"]
    for rank, row in enumerate(rows[:limit], start=1):
        lines.append(
            "| {rank} | `{group}` | {increase:.4f} | {rmse:.4f} | {r2:.3f} |".format(
                rank=rank,
                group=row["feature_group"],
                increase=float(row["rmse_increase"]),
                rmse=float(row["permuted_rmse"]),
                r2=float(row["permuted_r2"]),
            )
        )
    return "\n".join(lines)


def coefficient_lines(items: list[tuple[str, float]]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- `{name}`: {value:.3f}" for name, value in items)


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
    return f"""# Predictive Model: Daily Alert Hours

Threat type: `{threat_type}`  
Target: same-day alert hours per selected location and date  
Locations: {len(locations)} highest-total locations  
Date span: {min_day.isoformat()} to {max_day.isoformat()}  
Test window: {test_start.isoformat()} to {max_day.isoformat()}  
Model: dependency-free linear SGD regressor with chronological validation  
Training: {epochs} epochs, learning rate {learning_rate}  

## What The Model Is For

This is a predictive baseline for understanding which inputs help forecast alert hours. It is not a causal model: a feature can improve prediction without causing alarms, and a real cause can look weak if it is already captured by region/history.

{weather_note}

## Test Metrics

- Rows in test window: {full_metrics.rows:,}
- Mean target: {full_metrics.mean_target:.3f} h/day
- Mean prediction: {full_metrics.mean_prediction:.3f} h/day
- RMSE: {full_metrics.rmse:.3f} h/day
- MAE: {full_metrics.mae:.3f} h/day
- R2 vs train-mean baseline: {full_metrics.r2:.3f}

## Feature Importance By Permutation

Higher positive values mean the model got worse when that group was shuffled in the held-out test window, so that group helped prediction more. Negative or near-zero values mean the model did not rely on that feature group in this validation window.

{markdown_table(importance_rows)}

Full CSV: `{importance_display}`

## Reading The Result

Most important group in this run: `{best}`.

Use this ranking as evidence about predictive usefulness, not causality. In this run, recent alert history is the strongest signal, which means alert activity is temporally persistent. Weather variables can still be interesting, but if their permutation scores are small, they are not adding much beyond the model's geography, calendar, and recent-alert context.

## Largest Positive Non-Region Coefficients

{coefficient_lines(positives)}

## Largest Negative Non-Region Coefficients

{coefficient_lines(negatives)}
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
