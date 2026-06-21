"""Geocode alert locations to latitude/longitude with local caching.

This script is intentionally conservative with Nominatim/OpenStreetMap:

- one request at a time
- default 1.2 second pause between uncached requests
- custom User-Agent
- local CSV cache so repeated runs do not repeat the same geocoding

Output is written to `data/processed/location_geocodes.csv` by default. The
processed data folder is ignored by git, so the script is committed while the
generated geocode dataset stays local unless explicitly exported elsewhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "location_summary_clean.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "location_geocodes.csv"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "geocoding_summary.md"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AirAlertsProject/1.0 geocoding for academic analysis (https://github.com/timkaster/AirAlerts)"
MANUAL_QUERY_BY_SLUG = {
    "МогилівПодільський_район": "Могилів-Подільський район, Вінницька область, Україна",
    "КаміньКаширський_район": "Камінь-Каширський район, Волинська область, Україна",
    "ВолодимирВолинський_район": "Володимир-Волинський район, Волинська область, Україна",
}


@dataclass(frozen=True)
class Location:
    location_slug: str
    location_name: str
    threat_types: str
    interval_count: int
    total_duration_hours: float


def safe_float(value: object) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: object) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def load_locations(path: Path) -> list[Location]:
    grouped: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            slug = row["location_slug"]
            current = grouped.setdefault(
                slug,
                {
                    "location_slug": slug,
                    "location_name": row["location_name"],
                    "threat_types": set(),
                    "interval_count": 0,
                    "total_duration_hours": 0.0,
                },
            )
            threat_types = current["threat_types"]
            assert isinstance(threat_types, set)
            threat_types.add(row["threat_type"])
            current["interval_count"] = int(current["interval_count"]) + safe_int(row["interval_count"])
            current["total_duration_hours"] = float(current["total_duration_hours"]) + safe_float(row["total_duration_hours"])

    locations = [
        Location(
            location_slug=str(item["location_slug"]),
            location_name=str(item["location_name"]),
            threat_types=";".join(sorted(item["threat_types"])),
            interval_count=int(item["interval_count"]),
            total_duration_hours=float(item["total_duration_hours"]),
        )
        for item in grouped.values()
    ]
    return sorted(locations, key=lambda item: item.total_duration_hours, reverse=True)


def load_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["location_slug"]: row for row in csv.DictReader(handle)}


def clean_query_name(name: str) -> str:
    value = name.replace("м.", "").replace("м ", "")
    value = value.replace(" та ", " ")
    value = value.replace("територіальна громада", "")
    value = value.replace("територіальної громади", "")
    return " ".join(value.split()).strip(" ,.")


def primary_place_name(name: str) -> str:
    value = " ".join(name.split())
    if value.startswith("м. "):
        value = value.removeprefix("м. ")
    elif value.startswith("м "):
        value = value.removeprefix("м ")
    if " та " in value:
        value = value.split(" та ", 1)[0]
    return value.strip(" ,.")


def query_variants(location: Location) -> list[str]:
    manual_query = MANUAL_QUERY_BY_SLUG.get(location.location_slug)
    if manual_query:
        return [manual_query]
    cleaned = clean_query_name(location.location_name)
    primary = primary_place_name(location.location_name)
    variants = [
        f"{location.location_name}, Україна",
        f"{location.location_name}, Ukraine",
    ]
    if primary and primary != location.location_name:
        variants.extend([f"{primary}, Україна", f"{primary}, Ukraine"])
    if cleaned and cleaned != location.location_name:
        variants.extend([f"{cleaned}, Україна", f"{cleaned}, Ukraine"])
    return list(dict.fromkeys(variants))


def nominatim_search(query: str, timeout: int, max_retries: int) -> list[dict[str, object]]:
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": "5",
        "countrycodes": "ua",
        "accept-language": "uk,en",
        "addressdetails": "1",
    }
    url = f"{NOMINATIM_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(max_retries):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
            data = json.loads(payload)
            return data if isinstance(data, list) else []
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == max_retries - 1:
                raise
            time.sleep(10 * (attempt + 1))
        except URLError:
            if attempt == max_retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return []


def pick_result(results: list[dict[str, object]]) -> dict[str, object] | None:
    if not results:
        return None
    useful_types = {
        "administrative",
        "city",
        "town",
        "village",
        "municipality",
        "district",
        "county",
        "region",
        "province",
        "oblast",
    }
    useful_classes = {"boundary", "place"}
    poi_classes = {"amenity", "shop", "tourism", "leisure", "office", "building", "highway", "railway"}

    def score(result: dict[str, object]) -> tuple[int, int, float]:
        result_type = str(result.get("type", ""))
        result_class = str(result.get("class", ""))
        importance = safe_float(result.get("importance"))
        if result_class in poi_classes:
            class_score = -5
        elif result_class in useful_classes:
            class_score = 2
        else:
            class_score = 0
        type_score = 2 if result_type in useful_types else 0
        return (class_score, type_score, importance)

    return max(results, key=score)


def geocode_location(location: Location, timeout: int, max_retries: int, sleep_seconds: float) -> dict[str, str]:
    attempted: list[str] = []
    for query in query_variants(location):
        attempted.append(query)
        results = nominatim_search(query, timeout, max_retries)
        result = pick_result(results)
        time.sleep(sleep_seconds)
        if result:
            return row_from_result(location, query, result, "ok")
    return row_from_result(location, attempted[-1] if attempted else location.location_name, {}, "not_found")


def row_from_result(location: Location, query: str, result: dict[str, object], status: str) -> dict[str, str]:
    return {
        "location_slug": location.location_slug,
        "location_name": location.location_name,
        "threat_types": location.threat_types,
        "interval_count": str(location.interval_count),
        "total_duration_hours": f"{location.total_duration_hours:.3f}",
        "geocode_status": status,
        "query": query,
        "latitude": str(result.get("lat", "")),
        "longitude": str(result.get("lon", "")),
        "osm_type": str(result.get("osm_type", "")),
        "osm_id": str(result.get("osm_id", "")),
        "place_class": str(result.get("class", "")),
        "place_type": str(result.get("type", "")),
        "importance": str(result.get("importance", "")),
        "display_name": str(result.get("display_name", "")),
        "boundingbox": ";".join(str(value) for value in result.get("boundingbox", [])),
        "source": "OpenStreetMap Nominatim",
    }


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "location_slug",
        "location_name",
        "threat_types",
        "interval_count",
        "total_duration_hours",
        "geocode_status",
        "query",
        "latitude",
        "longitude",
        "osm_type",
        "osm_id",
        "place_class",
        "place_type",
        "importance",
        "display_name",
        "boundingbox",
        "source",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(output_path: Path, rows: list[dict[str, str]], report_path: Path) -> str:
    total = len(rows)
    ok = sum(1 for row in rows if row["geocode_status"] == "ok")
    missing = total - ok
    top_missing = [
        row
        for row in sorted(rows, key=lambda item: safe_float(item["total_duration_hours"]), reverse=True)
        if row["geocode_status"] != "ok"
    ][:15]

    missing_text = "\n".join(
        f"- {row['location_name']} (`{row['location_slug']}`), {safe_float(row['total_duration_hours']):.1f} alert h"
        for row in top_missing
    )
    if not missing_text:
        missing_text = "- none"

    output_display = display_path(output_path)

    return f"""# Location Geocoding Summary

Output: `{output_display}`  
Source: OpenStreetMap Nominatim  
Run type: cached, single-threaded geocoding

## Result

- Locations processed: {total}
- Geocoded successfully: {ok}
- Not found: {missing}
- Success rate: {(ok / total * 100) if total else 0:.1f}%

## Notes

Coordinates are suitable for exploratory spatial features. They are point coordinates from geocoding results, not official polygon centroids or area-weighted oblast centers.

Nominatim usage constraints followed by the script:

- one request at a time
- local result cache
- custom User-Agent
- default delay above one second between uncached requests

## Highest-Duration Missing Locations

{missing_text}

## Next Step

Use `{output_path.name}` to add latitude/longitude and nearby-region features to the predictive model, then compare against the current no-geocode baseline.
"""


def console_safe(value: str) -> str:
    return value.encode("ascii", errors="backslashreplace").decode("ascii")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=0, help="Limit uncached geocoding for testing. Use 0 for all.")
    parser.add_argument("--sleep-seconds", type=float, default=1.2)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-not-found", action="store_true", help="Retry cached not_found rows with current query rules.")
    args = parser.parse_args()

    locations = load_locations(args.input)
    cache = load_cache(args.output)
    rows_by_slug: dict[str, dict[str, str]] = {}
    uncached_count = 0

    for index, location in enumerate(locations, start=1):
        cached = cache.get(location.location_slug)
        if cached and not (args.retry_not_found and cached.get("geocode_status") == "not_found"):
            rows_by_slug[location.location_slug] = cached
            continue
        if args.limit and uncached_count >= args.limit:
            rows_by_slug[location.location_slug] = row_from_result(location, location.location_name, {}, "skipped")
            continue

        uncached_count += 1
        print(console_safe(f"[{index}/{len(locations)}] geocoding {location.location_name}"))
        rows_by_slug[location.location_slug] = geocode_location(
            location=location,
            timeout=args.timeout,
            max_retries=args.max_retries,
            sleep_seconds=args.sleep_seconds,
        )
        write_rows(args.output, list(rows_by_slug.values()))

    rows = [rows_by_slug[location.location_slug] for location in locations]
    write_rows(args.output, rows)
    report = render_report(args.output, rows, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(console_safe(report))


if __name__ == "__main__":
    main()
