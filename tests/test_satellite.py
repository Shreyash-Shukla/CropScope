import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
from PIL import Image

from location import validate_rectangle
from satellite import (
    BandWindow,
    NoSceneError,
    _fetch_thumbnail,
    _ndvi,
    _ndvi_png,
    _preview_png,
    _read_true_color,
    _savi,
    _true_color_png,
    compute_canopy_zones,
    fetch_satellite,
    search_scenes,
)


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


    def test_savi_and_canopy_zones(self):
        red = np.ma.array([[1000, 2000], [1500, 1000]])
        nir = np.ma.array([[3000, 2500], [2500, 1100]])
        scl = np.ma.array([[4, 4], [5, 5]])
        scale = (0.0001, 0.0)

        savi = _savi(red, nir, scl, scale, scale, l_factor=0.5)
        self.assertEqual(savi.shape, (2, 2))
        self.assertTrue(np.all(np.isfinite(savi.compressed())))

        ndvi_mock = np.ma.array([0.75, 0.45, 0.25, 0.10, -0.20])
        zones = compute_canopy_zones(ndvi_mock)
        self.assertEqual(zones["Dense Canopy (>0.60)"], 20.0)
        self.assertEqual(zones["Moderate Canopy (0.35-0.60)"], 20.0)
        self.assertEqual(zones["Sparse / Emerging (0.20-0.35)"], 20.0)
        self.assertEqual(zones["Bare Soil / Non-Vegetated (0.00-0.20)"], 20.0)
        self.assertEqual(zones["Water / Negative Index (<0.00)"], 20.0)

    def test_ndvi_png_colormaps(self):
        ndvi_mock = np.ma.array([[0.5, -0.2], [0.8, 0.1]])
        for cmap in ("agronomic", "viridis", "rdylgn"):
            png = _ndvi_png(ndvi_mock, colormap=cmap)
            img = Image.open(io.BytesIO(png))
            self.assertEqual(img.mode, "RGBA")
            self.assertEqual(img.size, (2, 2))

    def test_true_color_png_valid_and_transparency(self):
        rgb_data = np.ma.array([
            [[100, 150], [200, 250]],  # Red
            [[50, 75], [100, 125]],    # Green
            [[25, 35], [45, 55]],      # Blue
        ], dtype=np.uint8)
        rgb_data.mask = np.zeros(rgb_data.shape, dtype=bool)
        rgb_data.mask[:, 0, 1] = True  # Mask upper-right pixel

        png = _true_color_png(rgb_data)
        img = Image.open(io.BytesIO(png))
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.size, (2, 2))
        # Top-left pixel should be fully opaque
        self.assertEqual(img.getpixel((0, 0))[3], 255)
        self.assertEqual(img.getpixel((0, 0))[:3], (100, 50, 25))
        # Top-right pixel was masked, so alpha should be 0
        self.assertEqual(img.getpixel((1, 0))[3], 0)

    def test_fetch_thumbnail_success_and_error(self):
        with patch("satellite.urlopen", return_value=io.BytesIO(b"fake_jpeg_data")):
            data = _fetch_thumbnail("https://example.test/thumb.jpg")
            self.assertEqual(data, b"fake_jpeg_data")

        with patch("satellite.urlopen", side_effect=OSError("network down")):
            data = _fetch_thumbnail("https://example.test/thumb.jpg")
            self.assertIsNone(data)

    def test_fetch_satellite_with_true_color_and_telemetry(self):
        scene_item = self.item("with-tci", "2026-10-25T10:00:00Z", 2)
        scene_item["properties"]["platform"] = "sentinel-2a"
        scene_item["properties"]["view:sun_elevation"] = 42.5
        scene_item["properties"]["view:sun_azimuth"] = 160.2
        scene_item["properties"]["grid:code"] = "MGRS-43RFN"
        scene_item["assets"]["visual"] = {"href": "https://example.test/TCI.tif"}
        scene_item["assets"]["thumbnail"] = {"href": "https://example.test/L2A_PVI.jpg"}

        red_pixels = np.ma.array([[1500, 2000], [2500, 3000]])
        red_bw = BandWindow(red_pixels, None, None)
        classes = np.ma.array([[4, 5], [4, 5]])
        tci_pixels = np.ma.zeros((3, 2, 2), dtype=np.uint8)

        with patch("satellite.search_scenes", return_value=[scene_item]), \
             patch("satellite._read_band", return_value=red_bw), \
             patch("satellite._read_aligned_band", side_effect=[red_pixels, classes]), \
             patch("satellite._read_true_color", return_value=tci_pixels), \
             patch("satellite._fetch_thumbnail", return_value=b"thumb_bytes"):
            result = fetch_satellite(self.area)

        self.assertEqual(result.scene_id, "with-tci")
        self.assertIsNotNone(result.true_color_png)
        self.assertEqual(result.platform, "Sentinel-2A")
        self.assertEqual(result.sun_elevation, 42.5)
        self.assertEqual(result.sun_azimuth, 160.2)
        self.assertEqual(result.mgrs_tile, "MGRS-43RFN")
        self.assertEqual(result.scene_thumbnail_png, b"thumb_bytes")
        self.assertEqual(result.scene_thumbnail_url, "https://example.test/L2A_PVI.jpg")

    def test_fetch_satellite_graceful_when_visual_fails(self):
        scene_item = self.item("tci-fails", "2026-10-25T10:00:00Z", 2)
        scene_item["assets"]["visual"] = {"href": "https://example.test/TCI.tif"}

        red_pixels = np.ma.array([[1500, 2000], [2500, 3000]])
        red_bw = BandWindow(red_pixels, None, None)
        classes = np.ma.array([[4, 5], [4, 5]])

        with patch("satellite.search_scenes", return_value=[scene_item]), \
             patch("satellite._read_band", return_value=red_bw), \
             patch("satellite._read_aligned_band", side_effect=[red_pixels, classes]), \
             patch("satellite._read_true_color", side_effect=OSError("failed to fetch TCI")):
            result = fetch_satellite(self.area)

        # NDVI should still succeed even if visual failed
        self.assertEqual(result.scene_id, "tci-fails")
        self.assertIsNone(result.true_color_png)
        self.assertIsNotNone(result.ndvi_png)


if __name__ == "__main__":
    unittest.main()
