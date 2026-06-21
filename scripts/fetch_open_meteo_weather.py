"""Fetch daily weather features for one Ukrainian region from Open-Meteo.

This intentionally fetches only the weather feature currently used by the app:

- one requested region
- precipitation
- mean cloud cover

Use `--list-regions` to see accepted region slugs.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "weather_open_meteo.csv"
API_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEZONE = "Europe/Kyiv"
DAILY_VARIABLES = "precipitation_sum,cloud_cover_mean"


@dataclass(frozen=True)
class RegionPoint:
    region_slug: str
    region_name_en: str
    representative_place: str
    latitude: float
    longitude: float


REGION_POINTS = [
    RegionPoint("cherkasy_oblast", "Cherkasy Oblast", "Cherkasy", 49.4444, 32.0598),
    RegionPoint("chernihiv_oblast", "Chernihiv Oblast", "Chernihiv", 51.4982, 31.2893),
    RegionPoint("chernivtsi_oblast", "Chernivtsi Oblast", "Chernivtsi", 48.2915, 25.9403),
    RegionPoint("crimea", "Autonomous Republic of Crimea", "Simferopol", 44.9521, 34.1024),
    RegionPoint("dnipropetrovsk_oblast", "Dnipropetrovsk Oblast", "Dnipro", 48.4647, 35.0462),
    RegionPoint("donetsk_oblast", "Donetsk Oblast", "Donetsk", 48.0159, 37.8028),
    RegionPoint("ivano_frankivsk_oblast", "Ivano-Frankivsk Oblast", "Ivano-Frankivsk", 48.9226, 24.7111),
    RegionPoint("kharkiv_oblast", "Kharkiv Oblast", "Kharkiv", 49.9935, 36.2304),
    RegionPoint("kherson_oblast", "Kherson Oblast", "Kherson", 46.6354, 32.6169),
    RegionPoint("khmelnytskyi_oblast", "Khmelnytskyi Oblast", "Khmelnytskyi", 49.4229, 26.9871),
    RegionPoint("kirovohrad_oblast", "Kirovohrad Oblast", "Kropyvnytskyi", 48.5079, 32.2623),
    RegionPoint("kyiv_city", "Kyiv City", "Kyiv", 50.4501, 30.5234),
    RegionPoint("kyiv_oblast", "Kyiv Oblast", "Kyiv", 50.4501, 30.5234),
    RegionPoint("luhansk_oblast", "Luhansk Oblast", "Luhansk", 48.5740, 39.3078),
    RegionPoint("lviv_oblast", "Lviv Oblast", "Lviv", 49.8397, 24.0297),
    RegionPoint("mykolaiv_oblast", "Mykolaiv Oblast", "Mykolaiv", 46.9750, 31.9946),
    RegionPoint("odesa_oblast", "Odesa Oblast", "Odesa", 46.4825, 30.7233),
    RegionPoint("poltava_oblast", "Poltava Oblast", "Poltava", 49.5883, 34.5514),
    RegionPoint("rivne_oblast", "Rivne Oblast", "Rivne", 50.6199, 26.2516),
    RegionPoint("sevastopol_city", "Sevastopol City", "Sevastopol", 44.6167, 33.5254),
    RegionPoint("sumy_oblast", "Sumy Oblast", "Sumy", 50.9077, 34.7981),
    RegionPoint("ternopil_oblast", "Ternopil Oblast", "Ternopil", 49.5535, 25.5948),
    RegionPoint("vinnytsia_oblast", "Vinnytsia Oblast", "Vinnytsia", 49.2331, 28.4682),
    RegionPoint("volyn_oblast", "Volyn Oblast", "Lutsk", 50.7472, 25.3254),
    RegionPoint("zakarpattia_oblast", "Zakarpattia Oblast", "Uzhhorod", 48.6208, 22.2879),
    RegionPoint("zaporizhzhia_oblast", "Zaporizhzhia Oblast", "Zaporizhzhia", 47.8388, 35.1396),
    RegionPoint("zhytomyr_oblast", "Zhytomyr Oblast", "Zhytomyr", 50.2547, 28.6587),
]


REGIONS_BY_SLUG = {region.region_slug: region for region in REGION_POINTS}


def request_precipitation(region: RegionPoint, start_date: date, end_date: date, max_retries: int = 5) -> dict[str, object]:
    params = {
        "latitude": region.latitude,
        "longitude": region.longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": DAILY_VARIABLES,
        "timezone": TIMEZONE,
    }
    url = f"{API_URL}?{urlencode(params)}"
    for attempt in range(max_retries):
        try:
            with urlopen(url, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 429 or attempt == max_retries - 1:
                raise
            wait_seconds = 10 * (attempt + 1)
            print(f"Rate limited by Open-Meteo; waiting {wait_seconds}s before retry...")
            time.sleep(wait_seconds)
        except URLError:
            if attempt == max_retries - 1:
                raise
            wait_seconds = 5 * (attempt + 1)
            print(f"Network error; waiting {wait_seconds}s before retry...")
            time.sleep(wait_seconds)
    raise RuntimeError("Open-Meteo request failed")


def validate_range(start_date: date, end_date: date) -> int:
    if start_date > end_date:
        raise ValueError("start date must be before or equal to end date")
    return (end_date - start_date).days + 1


def build_rows(region: RegionPoint, payload: dict[str, object]) -> list[dict[str, object]]:
    daily = payload["daily"]
    assert isinstance(daily, dict)
    dates = daily["time"]
    precipitation = daily["precipitation_sum"]
    cloud_cover = daily["cloud_cover_mean"]
    assert isinstance(dates, list)
    assert isinstance(precipitation, list)
    assert isinstance(cloud_cover, list)

    rows: list[dict[str, object]] = []
    for day, precipitation_sum, cloud_cover_mean in zip(dates, precipitation, cloud_cover):
        rows.append(
            {
                "date_kyiv": day,
                "region_slug": region.region_slug,
                "region_name_en": region.region_name_en,
                "representative_place": region.representative_place,
                "latitude": region.latitude,
                "longitude": region.longitude,
                "precipitation_sum_mm": precipitation_sum,
                "cloud_cover_mean_percent": cloud_cover_mean,
                "source": "Open-Meteo Historical Weather API",
                "timezone": TIMEZONE,
            }
        )
    return rows


def write_rows(output_path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "date_kyiv",
        "region_slug",
        "region_name_en",
        "representative_place",
        "latitude",
        "longitude",
        "precipitation_sum_mm",
        "cloud_cover_mean_percent",
        "source",
        "timezone",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fetch_precipitation(region_slug: str, start_date: date, end_date: date, output_path: Path) -> None:
    validate_range(start_date, end_date)
    region = REGIONS_BY_SLUG.get(region_slug)
    if region is None:
        known = ", ".join(sorted(REGIONS_BY_SLUG))
        raise ValueError(f"unknown region slug {region_slug!r}. Known slugs: {known}")

    payload = request_precipitation(region, start_date, end_date)
    rows = build_rows(region, payload)
    write_rows(output_path, rows)
    print(f"Wrote {len(rows):,} weather rows to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-regions", action="store_true", help="Print accepted region slugs and exit.")
    parser.add_argument("--region-slug", help="One region slug to fetch, for example kyiv_city.")
    parser.add_argument("--start-date", type=date.fromisoformat, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", type=date.fromisoformat, help="End date, YYYY-MM-DD.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    if args.list_regions:
        for region in REGION_POINTS:
            print(f"{region.region_slug}: {region.region_name_en} ({region.representative_place})")
        return

    missing = [
        name
        for name, value in [
            ("--region-slug", args.region_slug),
            ("--start-date", args.start_date),
            ("--end-date", args.end_date),
        ]
        if value is None
    ]
    if missing:
        parser.error(f"required arguments unless --list-regions is used: {', '.join(missing)}")

    fetch_precipitation(args.region_slug, args.start_date, args.end_date, args.output)


if __name__ == "__main__":
    main()
