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


if __name__ == "__main__":
    unittest.main()

