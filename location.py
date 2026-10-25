"""Validate drawn or typed field-analysis rectangles."""

import math

from models import AnalysisArea


# About a 100 m square to a 3 km square. The upper bound keeps future 10 m
# satellite window reads small enough for an interactive classroom demo.
MIN_AREA_KM2 = 0.01
MAX_AREA_KM2 = 9.0
MAX_SIDE_KM = 5.0

SAMPLE_AREA = AnalysisArea(south=29.748, west=77.048, north=29.752, east=77.052)


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
