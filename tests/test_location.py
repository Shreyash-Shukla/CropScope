import json
import unittest

from location import (
    LocationError,
    SAMPLE_AREA,
    SAMPLE_PRESETS,
    area_to_geojson,
    generate_area_geojson_str,
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


if __name__ == "__main__":
    unittest.main()
