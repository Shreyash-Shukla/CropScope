import unittest

from location import LocationError, rectangle_from_geojson, validate_rectangle


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


if __name__ == "__main__":
    unittest.main()
