import json
import unittest

from unittest.mock import MagicMock, patch

from location import (
    LocationError,
    SAMPLE_AREA,
    SAMPLE_PRESETS,
    area_from_coordinates,
    area_to_geojson,
    generate_area_geojson_str,
    get_ip_location,
    parse_boundary_string,
    parse_coordinate_string,
    rectangle_from_geojson,
    search_locations,
    validate_rectangle,
)


class RectangleSelectionTests(unittest.TestCase):
    def test_drawn_rectangle_keeps_its_own_geometry(self):
        drawing = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.000, 47.000], [2.004, 47.000], [2.004, 47.004], [2.000, 47.004], [2.000, 47.000]]],
            },
        }
        area = rectangle_from_geojson(drawing)
        self.assertAlmostEqual(area.center[0], 47.002)
        self.assertAlmostEqual(area.center[1], 2.002)
        self.assertAlmostEqual(area.area_km2, 0.135, delta=0.01)
        self.assertAlmostEqual(area.area_ha, 13.5, delta=1.0)
        self.assertAlmostEqual(area.area_acres, 33.3, delta=2.5)
        self.assertIn("ha", area.formatted_area())
        self.assertIn("ac", area.formatted_area())
        self.assertIn("km²", area.formatted_area())

    def test_invalid_extents_and_sizes_are_rejected(self):
        invalid = [
            (47.004, 2.000, 47.000, 2.004),  # inverted latitudes
            (47.000, 2.004, 47.004, 2.000),  # inverted longitudes
            (47.000, 2.000, 47.00001, 2.00001),  # too small
            (47.000, 2.000, 48.000, 3.000),  # too large
            (0.000, 179.990, 0.004, -179.990),  # crosses the map boundary
        ]
        for coordinates in invalid:
            with self.subTest(coordinates=coordinates), self.assertRaises(LocationError):
                validate_rectangle(*coordinates)

    def test_non_rectangle_geojson_is_rejected(self):
        drawing = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.000, 47.000], [2.004, 47.000], [2.003, 47.004], [2.000, 47.004], [2.000, 47.000]]],
            },
        }
        with self.assertRaises(LocationError):
            rectangle_from_geojson(drawing)


    def test_sample_presets_are_valid(self):
        self.assertGreaterEqual(len(SAMPLE_PRESETS), 3)
        for name, preset in SAMPLE_PRESETS.items():
            validated = validate_rectangle(preset.south, preset.west, preset.north, preset.east)
            self.assertEqual(validated, preset)

    def test_area_to_geojson_and_roundtrip(self):
        feat = area_to_geojson(SAMPLE_AREA, "Test Field")
        self.assertEqual(feat["type"], "Feature")
        self.assertEqual(feat["geometry"]["type"], "Polygon")
        self.assertEqual(feat["properties"]["name"], "Test Field")
        self.assertIn("area_ha", feat["properties"])
        self.assertIn("bounds", feat["properties"])

        # Validate roundtrip back into rectangle_from_geojson
        reconstructed = rectangle_from_geojson(feat)
        self.assertAlmostEqual(reconstructed.south, SAMPLE_AREA.south, places=5)
        self.assertAlmostEqual(reconstructed.west, SAMPLE_AREA.west, places=5)
        self.assertAlmostEqual(reconstructed.north, SAMPLE_AREA.north, places=5)
        self.assertAlmostEqual(reconstructed.east, SAMPLE_AREA.east, places=5)

        # Validate string serialization
        json_str = generate_area_geojson_str(SAMPLE_AREA)
        loaded = json.loads(json_str)
        self.assertEqual(loaded["type"], "Feature")

    def test_area_from_coordinates_creates_valid_rectangle(self):
        area = area_from_coordinates(29.750, 77.050, side_km=0.5)
        self.assertAlmostEqual(area.center[0], 29.750, places=3)
        self.assertAlmostEqual(area.center[1], 77.050, places=3)
        self.assertGreaterEqual(area.area_km2, 0.20)
        self.assertLessEqual(area.area_km2, 0.30)

    def test_area_from_coordinates_invalid_inputs(self):
        with self.assertRaises(LocationError):
            area_from_coordinates(95.0, 77.0)  # Latitude out of bounds
        with self.assertRaises(LocationError):
            area_from_coordinates(29.0, 195.0)  # Longitude out of bounds
        with self.assertRaises(LocationError):
            area_from_coordinates(29.0, 77.0, side_km=10.0)  # Side too large

    def test_parse_coordinate_string_formats(self):
        # Standard decimal degrees
        lat, lon = parse_coordinate_string("29.7495, 77.0502")
        self.assertAlmostEqual(lat, 29.7495)
        self.assertAlmostEqual(lon, 77.0502)

        # Space separated
        lat, lon = parse_coordinate_string("48.25 1.70")
        self.assertAlmostEqual(lat, 48.25)
        self.assertAlmostEqual(lon, 1.70)

        # Cardinal directions with degree signs
        lat, lon = parse_coordinate_string("34.45 S, 146.05 E")
        self.assertAlmostEqual(lat, -34.45)
        self.assertAlmostEqual(lon, 146.05)

        lat, lon = parse_coordinate_string("48.25° N, 1.70° W")
        self.assertAlmostEqual(lat, 48.25)
        self.assertAlmostEqual(lon, -1.70)

        # Invalid formats
        with self.assertRaises(LocationError):
            parse_coordinate_string("invalid coordinates")
        with self.assertRaises(LocationError):
            parse_coordinate_string("100.0, 50.0")

    def test_parse_boundary_string_formats(self):
        # Labeled formats
        n, s, w, e = parse_boundary_string("North: 29.752, South: 29.748, West: 77.048, East: 77.052")
        self.assertAlmostEqual(n, 29.752)
        self.assertAlmostEqual(s, 29.748)
        self.assertAlmostEqual(w, 77.048)
        self.assertAlmostEqual(e, 77.052)

        n, s, w, e = parse_boundary_string("29.752 N, 29.748 S, 77.048 W, 77.052 E")
        self.assertAlmostEqual(n, 29.752)
        self.assertAlmostEqual(s, 29.748)
        self.assertAlmostEqual(w, 77.048)
        self.assertAlmostEqual(e, 77.052)

        # UI order: North, South, West, East
        n, s, w, e = parse_boundary_string("29.752, 29.748, 77.048, 77.052")
        self.assertAlmostEqual(n, 29.752)
        self.assertAlmostEqual(s, 29.748)
        self.assertAlmostEqual(w, 77.048)
        self.assertAlmostEqual(e, 77.052)

        # Leaflet bbox: South, West, North, East
        n, s, w, e = parse_boundary_string("29.748, 77.048, 29.752, 77.052")
        self.assertAlmostEqual(n, 29.752)
        self.assertAlmostEqual(s, 29.748)
        self.assertAlmostEqual(w, 77.048)
        self.assertAlmostEqual(e, 77.052)

        # Polygon coordinates
        poly_str = "[[77.048, 29.748], [77.052, 29.748], [77.052, 29.752], [77.048, 29.752]]"
        n, s, w, e = parse_boundary_string(poly_str)
        self.assertAlmostEqual(n, 29.752)
        self.assertAlmostEqual(s, 29.748)
        self.assertAlmostEqual(w, 77.048)
        self.assertAlmostEqual(e, 77.052)

        # Invalid formats and out of bounds
        with self.assertRaises(LocationError):
            parse_boundary_string("")
        with self.assertRaises(LocationError):
            parse_boundary_string("29.752, 77.048")
        with self.assertRaises(LocationError):
            parse_boundary_string("195.0, 29.748, 77.048, 77.052")

    @patch("urllib.request.urlopen")
    def test_get_ip_location_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "success",
            "lat": 28.6139,
            "lon": 77.2090,
            "city": "New Delhi",
            "regionName": "Delhi",
            "country": "India"
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        lat, lon, label = get_ip_location()
        self.assertAlmostEqual(lat, 28.6139)
        self.assertAlmostEqual(lon, 77.2090)
        self.assertIn("New Delhi", label)

    @patch("urllib.request.urlopen")
    def test_get_ip_location_failure(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Network unreachable")
        with self.assertRaises(LocationError):
            get_ip_location()

    @patch("urllib.request.urlopen")
    def test_search_locations_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": [
                {
                    "name": "Karnal",
                    "latitude": 29.69,
                    "longitude": 76.98,
                    "admin1": "Haryana",
                    "country": "India"
                }
            ]
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        results = search_locations("Karnal")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Karnal")
        self.assertAlmostEqual(results[0]["latitude"], 29.69)
        self.assertIn("Haryana", results[0]["label"])

    def test_search_locations_empty_query(self):
        self.assertEqual(search_locations(""), [])
        self.assertEqual(search_locations("   "), [])


if __name__ == "__main__":
    unittest.main()
