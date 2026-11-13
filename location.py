"""Validate drawn or typed field-analysis rectangles."""

import json
import math
import re

from models import AnalysisArea


# About a 100 m square to a 3 km square. The upper bound keeps future 10 m
# satellite window reads small enough for an interactive classroom demo.
MIN_AREA_KM2 = 0.01
MAX_AREA_KM2 = 9.0
MAX_SIDE_KM = 5.0

SAMPLE_PRESETS = {
    "Karnal, Haryana, India": AnalysisArea(south=29.748, west=77.048, north=29.752, east=77.052),
    "Beauce Region, France": AnalysisArea(south=48.248, west=1.698, north=48.252, east=1.702),
    "Riverina, NSW, Australia": AnalysisArea(south=-34.452, west=146.048, north=-34.448, east=146.052),
}
SAMPLE_AREA = SAMPLE_PRESETS["Karnal, Haryana, India"]


class LocationError(ValueError):
    """The selected rectangle cannot be used for this analysis."""


def validate_rectangle(south: float, west: float, north: float, east: float) -> AnalysisArea:
    values = (south, west, north, east)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise LocationError("Enter four finite numeric coordinates.")
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise LocationError("South must be below north, and west must be left of east. Rectangles crossing the 180° meridian are not supported; draw one side at a time.")

    area = AnalysisArea(float(south), float(west), float(north), float(east))
    north_south_km = 111.195 * (north - south)
    east_west_km = 111.195 * math.cos(math.radians(area.center[0])) * (east - west)
    if area.area_km2 < MIN_AREA_KM2:
        raise LocationError("This rectangle is too small for useful 10 m imagery. Enlarge it to at least 0.01 km² (about 1 hectare).")
    if area.area_km2 > MAX_AREA_KM2 or max(north_south_km, east_west_km) > MAX_SIDE_KM:
        raise LocationError("This rectangle is too large for a quick analysis. Reduce it to at most 9 km² and 5 km on each side.")
    return area


def rectangle_from_geojson(drawing: dict) -> AnalysisArea:
    """Accept only an axis-aligned GeoJSON rectangle from Folium Draw."""
    try:
        geometry = drawing.get("geometry", drawing)
        if geometry["type"] != "Polygon":
            raise LocationError("Use the rectangle tool to select an area.")
        ring = geometry["coordinates"][0]
        if len(ring) != 5 or any(len(point) < 2 for point in ring):
            raise LocationError("Draw one simple rectangle, then try again.")
        points = [(float(point[0]), float(point[1])) for point in ring]
    except LocationError:
        raise
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LocationError("The map returned an invalid rectangle. Clear it and draw again.") from exc

    if any(not math.isfinite(value) for point in points for value in point):
        raise LocationError("The map returned invalid coordinates. Clear the rectangle and draw again.")
    if points[0] != points[-1]:
        raise LocationError("The selected rectangle is not closed. Clear it and draw again.")

    corners = points[:-1]
    west, east = min(lon for lon, _ in corners), max(lon for lon, _ in corners)
    south, north = min(lat for _, lat in corners), max(lat for _, lat in corners)
    expected = {(west, south), (west, north), (east, south), (east, north)}
    if set(corners) != expected:
        raise LocationError("The selected shape is not a rectangle. Clear it and use Draw rectangle.")
    return validate_rectangle(south, west, north, east)


def area_to_geojson(area: AnalysisArea, name: str | None = None) -> dict:
    """Export an AnalysisArea as standard RFC 7946 GeoJSON Feature."""
    coordinates = [
        [round(area.west, 6), round(area.south, 6)],
        [round(area.east, 6), round(area.south, 6)],
        [round(area.east, 6), round(area.north, 6)],
        [round(area.west, 6), round(area.north, 6)],
        [round(area.west, 6), round(area.south, 6)],
    ]
    return {
        "type": "Feature",
        "properties": {
            "name": name or "CropScope Analysis Area",
            "area_km2": round(area.area_km2, 4),
            "area_ha": round(area.area_ha, 3),
            "area_acres": round(area.area_acres, 3),
            "center_latitude": round(area.center[0], 6),
            "center_longitude": round(area.center[1], 6),
            "bounds": {
                "south": round(area.south, 6),
                "west": round(area.west, 6),
                "north": round(area.north, 6),
                "east": round(area.east, 6),
            },
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates],
        },
    }


def generate_area_geojson_str(area: AnalysisArea, name: str | None = None) -> str:
    """Serialize the GeoJSON feature representation as formatted JSON string."""
    return json.dumps(area_to_geojson(area, name), indent=2)


def area_from_coordinates(latitude: float, longitude: float, side_km: float = 0.5) -> AnalysisArea:
    """Create an AnalysisArea square centered on (latitude, longitude) with side length in km.

    Default 0.5 km creates an approximate 25 ha field square, suitable for agricultural analysis.
    """
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise LocationError("Latitude and longitude must be numeric.")
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise LocationError("Latitude and longitude must be finite numbers.")
    if not (-90.0 <= latitude <= 90.0):
        raise LocationError(f"Latitude must be between -90 and 90 degrees (got {latitude}).")
    if not (-180.0 <= longitude <= 180.0):
        raise LocationError(f"Longitude must be between -180 and 180 degrees (got {longitude}).")
    if not (0.1 <= side_km <= MAX_SIDE_KM):
        raise LocationError(f"Field extent side must be between 0.1 km and {MAX_SIDE_KM} km.")

    half_side = side_km / 2.0
    delta_lat = half_side / 111.195
    cos_lat = math.cos(math.radians(latitude))
    delta_lon = half_side / (111.195 * max(cos_lat, 1e-4))

    south = max(-90.0, latitude - delta_lat)
    north = min(90.0, latitude + delta_lat)
    west = longitude - delta_lon
    east = longitude + delta_lon

    if west < -180.0 or east > 180.0:
        raise LocationError("Field rectangle crosses the 180° meridian, which is not supported; enter custom bounds.")

    return validate_rectangle(south, west, north, east)


def parse_coordinate_string(coord_str: str) -> tuple[float, float]:
    """Parse common coordinate string formats like '29.748, 77.048', '29.748° N, 77.048° E', etc.

    Returns (latitude, longitude) or raises LocationError.
    """
    if not coord_str or not coord_str.strip():
        raise LocationError("Enter coordinate text, e.g. '29.749, 77.050'.")
    cleaned = coord_str.strip()

    # Pattern for lat/lon with optional hemisphere letters N/S/E/W and degree symbols
    match = re.search(
        r"^\s*([+-]?\d+(?:\.\d+)?)\s*°?\s*([NSns])?\s*[,;/ ]\s*([+-]?\d+(?:\.\d+)?)\s*°?\s*([EWew])?\s*$",
        cleaned,
    )
    if match:
        lat_val = float(match.group(1))
        lat_dir = match.group(2)
        lon_val = float(match.group(3))
        lon_dir = match.group(4)
        if lat_dir and lat_dir.upper() == "S":
            lat_val = -abs(lat_val)
        elif lat_dir and lat_dir.upper() == "N":
            lat_val = abs(lat_val)
        if lon_dir and lon_dir.upper() == "W":
            lon_val = -abs(lon_val)
        elif lon_dir and lon_dir.upper() == "E":
            lon_val = abs(lon_val)
        if not (-90.0 <= lat_val <= 90.0):
            raise LocationError(f"Latitude {lat_val}° is out of bounds (-90° to 90°).")
        if not (-180.0 <= lon_val <= 180.0):
            raise LocationError(f"Longitude {lon_val}° is out of bounds (-180° to 180°).")
        return (lat_val, lon_val)

    # Standard comma or whitespace separated numbers
    parts = re.split(r"[,;\s]+", cleaned)
    if len(parts) == 2:
        try:
            lat_val, lon_val = float(parts[0]), float(parts[1])
            if not (-90.0 <= lat_val <= 90.0):
                raise LocationError(f"Latitude {lat_val}° is out of bounds (-90° to 90°).")
            if not (-180.0 <= lon_val <= 180.0):
                raise LocationError(f"Longitude {lon_val}° is out of bounds (-180° to 180°).")
            return (lat_val, lon_val)
        except ValueError:
            pass

    raise LocationError("Could not recognize coordinates. Examples: '29.7495, 77.0502' or '48.25 N, 1.70 E'.")


def get_ip_location(timeout: float = 3.0) -> tuple[float, float, str]:
    """Detect approximate location from public IP geolocation.

    Returns (latitude, longitude, display_name).
    Raises LocationError if geolocation fails or is unreachable.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    req = Request(
        "http://ip-api.com/json/",
        headers={"User-Agent": "CropScope/1.0 (Agricultural Remote Sensing)"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                lat = float(data["lat"])
                lon = float(data["lon"])
                city = data.get("city", "")
                region = data.get("regionName", "")
                country = data.get("country", "")
                parts = [p for p in (city, region, country) if p]
                label = ", ".join(parts) or "Current Network Location"
                return lat, lon, label
            raise LocationError("IP geolocation service did not return coordinates.")
    except (URLError, HTTPError, TimeoutError, ValueError, KeyError) as exc:
        raise LocationError(f"Could not automatically detect location: {exc}") from exc


def search_locations(query: str, count: int = 5, timeout: float = 4.0) -> list[dict]:
    """Search global locations by name using Open-Meteo Geocoding API.

    Returns a list of dictionaries with keys:
    'name', 'latitude', 'longitude', 'admin1', 'country', 'label'.
    """
    if not query or not query.strip():
        return []

    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    params = {
        "name": query.strip(),
        "count": max(1, min(count, 10)),
        "language": "en",
        "format": "json",
    }
    url = f"https://geocoding-api.open-meteo.com/v1/search?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "CropScope/1.0 (Agricultural Remote Sensing)"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_results = data.get("results", [])
            output = []
            for item in raw_results:
                name = item.get("name", "")
                admin1 = item.get("admin1", "")
                country = item.get("country", "")
                parts = [p for p in (name, admin1, country) if p]
                label = ", ".join(parts) or name
                output.append({
                    "name": name,
                    "latitude": float(item["latitude"]),
                    "longitude": float(item["longitude"]),
                    "admin1": admin1,
                    "country": country,
                    "label": label,
                })
            return output
    except (URLError, HTTPError, TimeoutError, ValueError, KeyError) as exc:
        raise LocationError(f"Location search failed: {exc}") from exc
