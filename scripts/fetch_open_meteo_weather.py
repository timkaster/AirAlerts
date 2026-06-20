"""Fetch daily regional weather proxies for Ukraine from Open-Meteo.

The output uses one representative point per Ukrainian region, usually the
regional capital. This is suitable for quick joins with alert time series. It
is not a polygon area-average; use ERA5-Land plus oblast boundaries if the
analysis needs physically area-weighted regional weather.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "weather_daily_regions_open_meteo.csv"
CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "open_meteo_weather"
API_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEZONE = "Europe/Kyiv"

DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_mean",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "shortwave_radiation_sum",
    "relative_humidity_2m_mean",
    "surface_pressure_mean",
]


@dataclass(frozen=True)
class RegionPoint:
    region_slug: str
    region_name_en: str
    region_name_uk: str
    representative_place: str
    latitude: float
    longitude: float


REGION_POINTS = [
    RegionPoint("cherkasy_oblast", "Cherkasy Oblast", "Черкаська область", "Cherkasy", 49.4444, 32.0598),
    RegionPoint("chernihiv_oblast", "Chernihiv Oblast", "Чернігівська область", "Chernihiv", 51.4982, 31.2893),
    RegionPoint("chernivtsi_oblast", "Chernivtsi Oblast", "Чернівецька область", "Chernivtsi", 48.2915, 25.9403),
    RegionPoint("crimea", "Autonomous Republic of Crimea", "Автономна Республіка Крим", "Simferopol", 44.9521, 34.1024),
    RegionPoint("dnipropetrovsk_oblast", "Dnipropetrovsk Oblast", "Дніпропетровська область", "Dnipro", 48.4647, 35.0462),
    RegionPoint("donetsk_oblast", "Donetsk Oblast", "Донецька область", "Donetsk", 48.0159, 37.8028),
    RegionPoint("ivano_frankivsk_oblast", "Ivano-Frankivsk Oblast", "Івано-Франківська область", "Ivano-Frankivsk", 48.9226, 24.7111),
    RegionPoint("kharkiv_oblast", "Kharkiv Oblast", "Харківська область", "Kharkiv", 49.9935, 36.2304),
    RegionPoint("kherson_oblast", "Kherson Oblast", "Херсонська область", "Kherson", 46.6354, 32.6169),
    RegionPoint("khmelnytskyi_oblast", "Khmelnytskyi Oblast", "Хмельницька область", "Khmelnytskyi", 49.4229, 26.9871),
    RegionPoint("kirovohrad_oblast", "Kirovohrad Oblast", "Кіровоградська область", "Kropyvnytskyi", 48.5079, 32.2623),
    RegionPoint("kyiv_city", "Kyiv City", "м. Київ", "Kyiv", 50.4501, 30.5234),
    RegionPoint("kyiv_oblast", "Kyiv Oblast", "Київська область", "Kyiv", 50.4501, 30.5234),
    RegionPoint("luhansk_oblast", "Luhansk Oblast", "Луганська область", "Luhansk", 48.5740, 39.3078),
    RegionPoint("lviv_oblast", "Lviv Oblast", "Львівська область", "Lviv", 49.8397, 24.0297),
    RegionPoint("mykolaiv_oblast", "Mykolaiv Oblast", "Миколаївська область", "Mykolaiv", 46.9750, 31.9946),
    RegionPoint("odesa_oblast", "Odesa Oblast", "Одеська область", "Odesa", 46.4825, 30.7233),
    RegionPoint("poltava_oblast", "Poltava Oblast", "Полтавська область", "Poltava", 49.5883, 34.5514),
    RegionPoint("rivne_oblast", "Rivne Oblast", "Рівненська область", "Rivne", 50.6199, 26.2516),
    RegionPoint("sevastopol_city", "Sevastopol City", "м. Севастополь", "Sevastopol", 44.6167, 33.5254),
    RegionPoint("sumy_oblast", "Sumy Oblast", "Сумська область", "Sumy", 50.9077, 34.7981),
    RegionPoint("ternopil_oblast", "Ternopil Oblast", "Тернопільська область", "Ternopil", 49.5535, 25.5948),
    RegionPoint("vinnytsia_oblast", "Vinnytsia Oblast", "Вінницька область", "Vinnytsia", 49.2331, 28.4682),
    RegionPoint("volyn_oblast", "Volyn Oblast", "Волинська область", "Lutsk", 50.7472, 25.3254),
    RegionPoint("zakarpattia_oblast", "Zakarpattia Oblast", "Закарпатська область", "Uzhhorod", 48.6208, 22.2879),
    RegionPoint("zaporizhzhia_oblast", "Zaporizhzhia Oblast", "Запорізька область", "Zaporizhzhia", 47.8388, 35.1396),
    RegionPoint("zhytomyr_oblast", "Zhytomyr Oblast", "Житомирська область", "Zhytomyr", 50.2547, 28.6587),
]


def request_chunk(regions: list[RegionPoint], start_date: date, end_date: date, max_retries: int = 8) -> list[dict[str, object]]:
    params = {
        "latitude": ",".join(str(region.latitude) for region in regions),
        "longitude": ",".join(str(region.longitude) for region in regions),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
    }
    url = f"{API_URL}?{urlencode(params)}"
    for attempt in range(max_retries):
        try:
            with urlopen(url, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            if exc.code != 429 or attempt == max_retries - 1:
                raise
            wait_seconds = min(180, 20 * (attempt + 1))
            print(f"Rate limited by Open-Meteo; waiting {wait_seconds}s before retry...")
            time.sleep(wait_seconds)
        except URLError:
            if attempt == max_retries - 1:
                raise
            wait_seconds = 5 * (attempt + 1)
            print(f"Network error; waiting {wait_seconds}s before retry...")
            time.sleep(wait_seconds)
    if isinstance(payload, dict):
        payload = [payload]
    return payload


def build_rows(regions: list[RegionPoint], payload: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for region, item in zip(regions, payload):
        daily = item["daily"]
        assert isinstance(daily, dict)
        dates = daily["time"]
        assert isinstance(dates, list)
        for index, day in enumerate(dates):
            row: dict[str, object] = {
                "date_kyiv": day,
                "region_slug": region.region_slug,
                "region_name_en": region.region_name_en,
                "region_name_uk": region.region_name_uk,
                "representative_place": region.representative_place,
                "latitude": region.latitude,
                "longitude": region.longitude,
                "source": "Open-Meteo Historical Weather API",
                "timezone": TIMEZONE,
            }
            for variable in DAILY_VARIABLES:
                values = daily.get(variable)
                if isinstance(values, list):
                    row[variable] = values[index]
                else:
                    row[variable] = ""
            rows.append(row)
    return rows


def cache_path(cache_dir: Path, region: RegionPoint, start_date: date, end_date: date) -> Path:
    date_part = f"{start_date.isoformat()}_{end_date.isoformat()}"
    safe_region = re.sub(r"[^a-z0-9_]+", "_", region.region_slug)
    return cache_dir / f"{safe_region}_{date_part}.json"


def fetch_weather(
    start_date: date,
    end_date: date,
    output_path: Path,
    chunk_size: int,
    cache_dir: Path,
    sleep_seconds: float,
) -> None:
    all_rows: list[dict[str, object]] = []
    cache_dir.mkdir(parents=True, exist_ok=True)

    for offset in range(0, len(REGION_POINTS), chunk_size):
        chunk = REGION_POINTS[offset : offset + chunk_size]
        payload: list[dict[str, object]] = []
        missing: list[RegionPoint] = []

        for region in chunk:
            path = cache_path(cache_dir, region, start_date, end_date)
            if path.exists():
                payload.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                missing.append(region)

        if missing:
            fetched = request_chunk(missing, start_date, end_date)
            for region, item in zip(missing, fetched):
                path = cache_path(cache_dir, region, start_date, end_date)
                path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
            fetched_by_slug = {region.region_slug: item for region, item in zip(missing, fetched)}
            payload = [
                json.loads(cache_path(cache_dir, region, start_date, end_date).read_text(encoding="utf-8"))
                if region.region_slug not in fetched_by_slug
                else fetched_by_slug[region.region_slug]
                for region in chunk
            ]
            time.sleep(sleep_seconds)

        all_rows.extend(build_rows(chunk, payload))

    fieldnames = [
        "date_kyiv",
        "region_slug",
        "region_name_en",
        "region_name_uk",
        "representative_place",
        "latitude",
        "longitude",
        "source",
        "timezone",
        *DAILY_VARIABLES,
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {len(all_rows):,} rows to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=lambda value: date.fromisoformat(value), default=date(2022, 6, 21))
    parser.add_argument("--end-date", type=lambda value: date.fromisoformat(value), default=date(2026, 6, 20))
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--chunk-size", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--sleep-seconds", type=float, default=15.0)
    args = parser.parse_args()
    fetch_weather(args.start_date, args.end_date, args.output, args.chunk_size, args.cache_dir, args.sleep_seconds)


if __name__ == "__main__":
    main()
