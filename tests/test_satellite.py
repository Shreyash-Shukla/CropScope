import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
from PIL import Image

from location import validate_rectangle
from satellite import BandWindow, NoSceneError, _ndvi, _preview_png, fetch_satellite, search_scenes


class SatelliteTests(unittest.TestCase):
    def setUp(self):
        self.area = validate_rectangle(47.000, 2.000, 47.004, 2.004)
        self.now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)

    def item(self, scene_id, date, cloud):
        return {
            "id": scene_id,
            "collection": "sentinel-2-c1-l2a",
            "properties": {"datetime": date, "eo:cloud_cover": cloud},
            "assets": {
                "red": {"href": f"https://example.test/{scene_id}/B04.tif", "raster:bands": [{"scale": 0.0001, "offset": -0.1}]},
                "nir": {"href": f"https://example.test/{scene_id}/B08.tif", "raster:bands": [{"scale": 0.0001, "offset": -0.1}]},
                "scl": {"href": f"https://example.test/{scene_id}/SCL.tif"},
            },
        }

    def test_search_uses_whole_rectangle_and_prefers_suitable_scene(self):
        cloudy = self.item("cloudy", "2026-10-29T10:00:00Z", 88)
        clear = self.item("clear", "2026-10-25T10:00:00Z", 1)
        response = io.BytesIO(json.dumps({"features": [cloudy, clear]}).encode())
        with patch("satellite.urlopen", return_value=response) as open_url:
            found = search_scenes(self.area, now=self.now)
        query = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(query["bbox"], [2.0, 47.0, 2.004, 47.004])
        self.assertEqual(query["collections"], ["sentinel-2-c1-l2a"])
        self.assertEqual([item["id"] for item in found], ["clear"])

    def test_missing_scenes_and_outside_coverage_are_honest(self):
        with patch("satellite.search_scenes", return_value=[]):
            with self.assertRaisesRegex(NoSceneError, "No recent"):
                fetch_satellite(self.area)
        polar = validate_rectangle(84.4, 2.0, 84.404, 2.02)
        with self.assertRaisesRegex(NoSceneError, "outside Sentinel-2"):
            fetch_satellite(polar)

    def test_failed_first_scene_tries_next_without_changing_area(self):
        first = self.item("partial", "2026-10-29T10:00:00Z", 1)
        second = self.item("complete", "2026-10-25T10:00:00Z", 2)
        pixels = np.ma.array([[1500, 2000], [2500, 3000]])
        red = BandWindow(pixels, None, None)
        classes = np.ma.array([[4, 5], [4, 5]])
        with patch("satellite.search_scenes", return_value=[first, second]), patch(
            "satellite._read_band", side_effect=[NoSceneError("partial"), red]
        ) as read_band, patch("satellite._read_aligned_band", side_effect=[pixels, classes]):
            result = fetch_satellite(self.area)
        self.assertEqual(result.scene_id, "complete")
        self.assertEqual(result.area, self.area)
        self.assertEqual(read_band.call_args.args[1], self.area)
        self.assertEqual(result.width, 2)
        self.assertEqual(result.valid_pixel_percent, 100)
        self.assertIsNotNone(result.ndvi_png)

    def test_scale_offset_mask_and_zero_denominator(self):
        red = np.ma.array([[2000, 2000, 1000, 2000, 2000]], mask=[[False, False, False, True, False]])
        nir = np.ma.array([[4000, 4000, 1000, 4000, 500]])
        scl = np.ma.array([[4, 9, 4, 4, 5]])
        result = _ndvi(red, nir, scl, (0.0001, -0.1), (0.0001, -0.1))
        self.assertAlmostEqual(result[0, 0], 0.5)
        self.assertEqual(result.count(), 1)

    def test_all_cloudy_scene_returns_quality_message(self):
        item = self.item("cloudy-here", "2026-10-25T10:00:00Z", 2)
        pixels = np.ma.array([[1500, 2000], [2500, 3000]])
        red = BandWindow(pixels, None, None)
        classes = np.ma.array([[8, 9], [3, 10]])
        with patch("satellite.search_scenes", return_value=[item]), patch(
            "satellite._read_band", return_value=red
        ), patch("satellite._read_aligned_band", side_effect=[pixels, classes]):
            result = fetch_satellite(self.area)
        self.assertEqual(result.valid_pixel_percent, 0)
        self.assertIsNone(result.mean_ndvi)
        self.assertIsNone(result.ndvi_png)
        self.assertIn("Too few clear", result.quality_message)

    def test_cloudy_first_scene_tries_clearer_candidate(self):
        first = self.item("cloudy-here", "2026-10-29T10:00:00Z", 1)
        second = self.item("clear-here", "2026-10-25T10:00:00Z", 2)
        pixels = np.ma.array([[1500, 2000], [2500, 3000]])
        red = BandWindow(pixels, None, None)
        cloudy = np.ma.array([[8, 9], [3, 10]])
        clear = np.ma.array([[4, 5], [4, 5]])
        with patch("satellite.search_scenes", return_value=[first, second]), patch(
            "satellite._read_band", return_value=red
        ) as read_band, patch("satellite._read_aligned_band", side_effect=[pixels, cloudy, pixels, clear]):
            result = fetch_satellite(self.area)
        self.assertEqual(result.scene_id, "clear-here")
        self.assertEqual(result.valid_pixel_percent, 100)
        self.assertEqual(read_band.call_count, 2)

    def test_preview_preserves_nodata_transparency(self):
        pixels = np.ma.array([[10, 20], [30, 40]], mask=[[False, True], [False, False]])
        png = _preview_png(pixels)
        image = Image.open(io.BytesIO(png))
        self.assertEqual(image.mode, "LA")
        self.assertEqual(image.getpixel((1, 0))[1], 0)
        self.assertEqual(image.getpixel((0, 0))[1], 255)


if __name__ == "__main__":
    unittest.main()
