# Location Geocoding Summary

Output: `data\processed\location_geocodes.csv`  
Source: OpenStreetMap Nominatim  
Run type: cached, single-threaded geocoding

## Result

- Locations processed: 273
- Geocoded successfully: 273
- Not found: 0
- Success rate: 100.0%

## Notes

Coordinates are suitable for exploratory spatial features. They are point coordinates from geocoding results, not official polygon centroids or area-weighted oblast centers.

Nominatim usage constraints followed by the script:

- one request at a time
- local result cache
- custom User-Agent
- default delay above one second between uncached requests

## Highest-Duration Missing Locations

- none

## Next Step

Use `location_geocodes.csv` to add latitude/longitude and nearby-region features to the predictive model, then compare against the current no-geocode baseline.
