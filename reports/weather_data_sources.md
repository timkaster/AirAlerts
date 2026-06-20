# Historic Weather Data Sources For Ukraine

Goal: daily precipitation for the requested Ukrainian region and modeling window, suitable for joining to the air-alert dataset.

## Recommended Source: Open-Meteo Historical Weather API

Use Open-Meteo for the project dataset.

- Coverage: global historical weather.
- Resolution: daily variables are available from hourly/reanalysis sources.
- Practical access: no API key required for normal use.
- Data basis: ERA5, ERA5-Land, and ECMWF IFS reanalysis/model products depending on variable and period.
- Best project fit: easy to automate, daily resolution, and precise small-range requests.

Project script:

```powershell
python scripts\fetch_open_meteo_weather.py `
  --region-slug kyiv_city `
  --start-date 2026-05-01 `
  --end-date 2026-05-31 `
  --output data\processed\weather_precipitation_open_meteo.csv
```

The script fetches only `precipitation_sum` for one region and refuses inclusive date ranges longer than 59 days. It uses one representative point per region, usually the regional capital. This is a regional proxy, not an area-weighted oblast average.

## Stronger But Heavier Alternative: ERA5-Land

Use ERA5-Land through Copernicus Climate Data Store or Google Earth Engine if the final analysis needs true area averages over oblast polygons.

- Coverage: 1950 to near-present.
- Spatial resolution: about 9 km.
- Temporal resolution: hourly source data, can be aggregated to daily.
- Tradeoff: best scientific option, but requires heavier tooling and region boundary polygons.

## Other Useful Alternatives

### NASA POWER Daily API

Good if you want easy daily meteorological variables by point and can accept a coarser global grid.

### Meteostat

Good for station-based or interpolated daily weather. It is convenient in Python, but station coverage and wartime station gaps may be less consistent than reanalysis.

## Current Project Decision

Use Open-Meteo first because it is fast to integrate for the only weather feature currently needed: daily precipitation.

If weather becomes a central explanatory variable in the final report, validate the most important findings against ERA5-Land area averages.
