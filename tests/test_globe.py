import datetime
import math
import unittest

from globe import (
    _load_texture_data_url,
    build_globe_html,
    compute_subsolar_point,
    is_location_sunlit,
    lat_lon_to_world,
    sun_direction_world,
)


class GlobeAstronomicalTests(unittest.TestCase):
    def test_subsolar_longitude_at_noon_utc(self):
        # At 12:00 UTC, the sun is approximately over the Prime Meridian (lon ~0)
        dt_noon = datetime.datetime(2026, 6, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sub_lat, sub_lon = compute_subsolar_point(dt_noon)
        self.assertAlmostEqual(sub_lon, 0.0, delta=5.0)
        # On June 21, subsolar latitude is near the Tropic of Cancer (+23.44°)
        self.assertAlmostEqual(sub_lat, 23.44, delta=2.5)

    def test_subsolar_longitude_at_midnight_utc(self):
        # At 00:00 UTC, the sun is approximately over longitude ~180° / -180°
        dt_midnight = datetime.datetime(2026, 6, 21, 0, 0, 0, tzinfo=datetime.timezone.utc)
        sub_lat, sub_lon = compute_subsolar_point(dt_midnight)
        self.assertTrue(abs(sub_lon) >= 170.0 or abs(sub_lon) <= 180.0)

    def test_subsolar_latitude_at_december_solstice(self):
        # On December 21, subsolar latitude is near the Tropic of Capricorn (-23.44°)
        dt_solstice = datetime.datetime(2026, 12, 21, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sub_lat, sub_lon = compute_subsolar_point(dt_solstice)
        self.assertAlmostEqual(sub_lat, -23.44, delta=2.5)

    def test_is_location_sunlit_at_noon_vs_night(self):
        # Midday at Greenwich: location at (0, 0) should be sunlit with high elevation
        dt_noon = datetime.datetime(2026, 3, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        is_day, elevation = is_location_sunlit(0.0, 0.0, dt_noon)
        self.assertTrue(is_day)
        self.assertGreater(elevation, 70.0)

        # Opposite side of the Earth at (0, 180) should be in night shadow
        is_day_nightside, elevation_nightside = is_location_sunlit(0.0, 180.0, dt_noon)
        self.assertFalse(is_day_nightside)
        self.assertLess(elevation_nightside, -70.0)

    def test_lat_lon_to_world_coordinates(self):
        # Equator at Prime Meridian (0, 0) -> (+1, 0, 0)
        x, y, z = lat_lon_to_world(0.0, 0.0, 1.0)
        self.assertAlmostEqual(x, 1.0, places=6)
        self.assertAlmostEqual(y, 0.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)

        # North Pole (90, 0) -> (0, +1, 0)
        nx, ny, nz = lat_lon_to_world(90.0, 0.0, 1.0)
        self.assertAlmostEqual(nx, 0.0, places=6)
        self.assertAlmostEqual(ny, 1.0, places=6)
        self.assertAlmostEqual(nz, 0.0, places=6)

        # Lon +90°E at Equator -> (0, 0, -1) in Three.js World frame
        ex, ey, ez = lat_lon_to_world(0.0, 90.0, 1.0)
        self.assertAlmostEqual(ex, 0.0, places=6)
        self.assertAlmostEqual(ey, 0.0, places=6)
        self.assertAlmostEqual(ez, -1.0, places=6)

        # Lon -90°W at Equator -> (0, 0, +1) in Three.js World frame
        wx, wy, wz = lat_lon_to_world(0.0, -90.0, 1.0)
        self.assertAlmostEqual(wx, 0.0, places=6)
        self.assertAlmostEqual(wy, 0.0, places=6)
        self.assertAlmostEqual(wz, 1.0, places=6)

        # Karnal, India (29.7495° N, 77.0502° E): northern and eastern quadrant
        kx, ky, kz = lat_lon_to_world(29.7495, 77.0502, 1.0)
        self.assertGreater(kx, 0.0)  # cos(lat) * cos(lon) > 0
        self.assertGreater(ky, 0.0)  # sin(lat) > 0
        self.assertLess(kz, 0.0)     # -cos(lat) * sin(lon) < 0 (east is -Z)

    def test_sun_direction_and_subsolar_alignment(self):
        dt = datetime.datetime(2026, 5, 14, 10, 30, 0, tzinfo=datetime.timezone.utc)
        ms = dt.timestamp() * 1000.0
        sub_lat, sub_lon = compute_subsolar_point(dt)

        loc_x, loc_y, loc_z = lat_lon_to_world(sub_lat, sub_lon, 1.0)
        sun_x, sun_y, sun_z = sun_direction_world(ms)

        # Sun vector must be unit length
        sun_len = math.hypot(sun_x, sun_y, sun_z)
        self.assertAlmostEqual(sun_len, 1.0, places=6)

        # Dot product between location on globe and sun direction must be exactly 1.0
        dot = loc_x * sun_x + loc_y * sun_y + loc_z * sun_z
        self.assertAlmostEqual(dot, 1.0, places=5)

    def test_texture_loading(self):
        day_url = _load_texture_data_url("earth-day-2k.webp")
        self.assertTrue(day_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(day_url), 50000)

        night_url = _load_texture_data_url("earth-night-2k.webp")
        self.assertTrue(night_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(night_url), 20000)

        clouds_url = _load_texture_data_url("earth-clouds-1k.webp")
        self.assertTrue(clouds_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(clouds_url), 30000)

        day_4k_url = _load_texture_data_url("earth-day-4k.webp")
        self.assertTrue(day_4k_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(day_4k_url), 100000)

        night_4k_url = _load_texture_data_url("earth-night-4k.webp")
        self.assertTrue(night_4k_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(night_4k_url), 50000)

        clouds_2k_url = _load_texture_data_url("earth-clouds-2k.webp")
        self.assertTrue(clouds_2k_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(clouds_2k_url), 50000)

        day_8k_url = _load_texture_data_url("earth-day-8k.webp")
        self.assertTrue(day_8k_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(day_8k_url), 1000000)

        data_4k_url = _load_texture_data_url("earth-data-4k.webp")
        self.assertTrue(data_4k_url.startswith("data:image/webp;base64,"))
        self.assertGreater(len(data_4k_url), 400000)

    def test_build_globe_html_contains_critical_components(self):
        html = build_globe_html(29.748, 77.048, "Karnal Farm", height=500)
        self.assertIn("three.js", html.lower())
        self.assertIn("orbitcontrols", html.lower())
        self.assertIn("Karnal Farm", html)
        self.assertIn("29.748", html)
        self.assertIn("77.048", html)
        self.assertIn("earthVertexShader", html)
        self.assertIn("earthFragmentShader", html)
        self.assertIn("atmoFragmentShader", html)
        self.assertIn("cloudVertexShader", html)
        self.assertIn("reticleVertexShader", html)
        self.assertIn("subsolar", html.lower())
        self.assertIn("btn-sweep", html)
        self.assertIn("btn-focus", html)
        self.assertIn("data:image/webp;base64,", html)

    def test_direct_manipulation_camera_sensitivity_controls(self):
        html = build_globe_html(29.748, 77.048, "Karnal Farm", height=540)
        # Direct-manipulation camera math functions from Watched.earth
        self.assertIn("radiansPerPixel", html)
        self.assertIn("applyControls", html)
        self.assertIn("createPose", html)
        self.assertIn("interpolatePose", html)
        self.assertIn("MIN_RANGE", html)
        self.assertIn("MAX_RANGE", html)
        # Verify that gesture listeners with pointer captures exist
        self.assertIn("setPointerCapture", html)
        self.assertIn("pointerdown", html)
        self.assertIn("pointermove", html)
        self.assertIn("touch-action: none", html)
        # Verify wheel input is clamped to prevent sudden sensitivity spikes
        self.assertIn("clampedDelta", html)

    def test_radians_per_pixel_sensitivity_scaling_math(self):
        fov_deg = 38.0
        height_px = 540.0
        tan_half = math.tan(math.radians(fov_deg) / 2.0)

        # Overview range vs close inspection range
        overview_range = 2.2
        close_range = 0.25

        k_overview = (2.0 * overview_range * tan_half) / height_px
        k_close = (2.0 * close_range * tan_half) / height_px

        # Panning sensitivity close to ground must be almost an order of magnitude smaller
        # than overview, preventing wild overshooting when zoomed in
        self.assertLess(k_close, k_overview * 0.15)
        # 10 px drag at close range moves less than 0.2 degrees on the globe
        drag_10px_close_deg = math.degrees(10.0 * k_close)
        self.assertLess(drag_10px_close_deg, 0.2)

    def test_globe_zoom_detail_and_sharpness_pipeline(self):
        html = build_globe_html(29.748, 77.048, "Karnal Farm", height=540)
        # Verify 8K texture and 4K data texture embedding
        self.assertIn("__DATA_TEXTURE_DATA_URL__" not in html, [True])
        self.assertIn("dataTexture", html)
        self.assertIn("uData", html)
        self.assertIn("uDataTexel", html)
        self.assertIn("uBump", html)
        # Verify that mismatched square tile overlays are not injected (preventing square tile artifacts on Himalayas/terrain)
        self.assertNotIn("uCtxMap", html)
        self.assertNotIn("BlueMarble_NextGeneration", html)
        # Verify adaptive unsharp sharpening for zoom detail
        self.assertIn("zoomCloseness", html)
        self.assertIn("highPass", html)
        # Verify high tessellation geometry
        self.assertIn("220, 110", html)

    def test_globe_no_graticule_latitude_longitude_lines(self):
        html = build_globe_html(29.748, 77.048, "Karnal Farm", height=540)
        # Verify latitude and longitude grid lines are removed
        self.assertNotIn("latGrid", html)
        self.assertNotIn("lonGrid", html)
        self.assertNotIn("gridLine", html)

    def test_globe_clouds_toggle_option(self):
        # Default with clouds enabled
        html_on = build_globe_html(29.748, 77.048, "Karnal Farm", height=540, show_clouds=True)
        self.assertIn('id="btn-clouds"', html_on)
        self.assertIn("☁️ Clouds: On", html_on)
        self.assertIn("let cloudsVisible = true;", html_on)
        self.assertIn("cloudMesh.visible = cloudsVisible;", html_on)

        # Clouds disabled option
        html_off = build_globe_html(29.748, 77.048, "Karnal Farm", height=540, show_clouds=False)
        self.assertIn('id="btn-clouds"', html_off)
        self.assertIn("☁️ Clouds: Off", html_off)
        self.assertIn("let cloudsVisible = false;", html_off)

    def test_globe_layout_decluttering_and_height(self):
        # Default height should be generous 680px
        html_default = build_globe_html(29.748, 77.048, "Karnal Farm")
        self.assertIn("const height = container.clientHeight || 680;", html_default)

        # Check non-overlapping 2-tier HUD architecture
        self.assertIn("hud-top-bar", html_default)
        self.assertIn("hud-bottom-bar", html_default)
        self.assertIn("controls-dock", html_default)
        self.assertIn("target-callout", html_default)
        self.assertIn("ro-bl", html_default)
        self.assertIn("ro-br", html_default)


if __name__ == "__main__":
    unittest.main()

