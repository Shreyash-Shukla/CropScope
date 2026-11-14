import datetime
import unittest

from globe import build_globe_html, compute_subsolar_point, is_location_sunlit


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
        self.assertTrue(abs(sub_lon) >= 175.0 or abs(sub_lon) <= 180.0)

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
        self.assertIn("subsolar", html.lower())


if __name__ == "__main__":
    unittest.main()
