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
    parse_coordinate_string,
    rectangle_from_geojson,
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


if __name__ == "__main__":
    unittest.main()
