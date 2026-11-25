import io
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from location import validate_rectangle
from weather import WeatherError, fetch_weather, parse_weather


def forecast_payload():
    return {
        "latitude": 48.1,
        "longitude": 2.1,
        "timezone": "Europe/Paris",
        "daily_units": {
            "rain_sum": "mm",
            "temperature_2m_max": "°C",
            "et0_fao_evapotranspiration": "mm",
        },
        "daily": {
            "time": [
                "2026-10-29",
                "2026-10-30",
                "2026-10-31",
                "2026-11-01",
                "2026-11-02",
                "2026-11-03",
                "2026-11-04",
            ],
            "rain_sum": [0.0, 0.2, 1.1, 0.0, 0.0, 0.5, 0.0],
            "temperature_2m_max": [13.0, 14.0, 12.0, 11.0, 13.0, 15.0, 14.0],
            "et0_fao_evapotranspiration": [1.1, 1.2, 0.9, 0.8, 1.0, 1.3, 1.2],
        },
    }


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.area = validate_rectangle(48.100, 2.100, 48.104, 2.105)
        self.now = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)

    def test_complete_response_produces_seven_dated_rows(self):
        result = parse_weather(forecast_payload(), self.area, "https://example.test", self.now)
        self.assertEqual(len(result.days), 7)
        self.assertEqual(result.days[3].day.isoformat(), "2026-11-01")
        self.assertEqual(result.days[2].rain_mm, 1.1)

    def test_incomplete_and_nonconsecutive_responses_are_rejected(self):
        incomplete = forecast_payload()
        incomplete["daily"]["rain_sum"] = incomplete["daily"]["rain_sum"][:-1]
        with self.assertRaises(WeatherError):
            parse_weather(incomplete, self.area, "https://example.test", self.now)

        nonconsecutive = forecast_payload()
        nonconsecutive["daily"]["time"][3] = "2026-11-02"
        with self.assertRaises(WeatherError):
            parse_weather(nonconsecutive, self.area, "https://example.test", self.now)

    def test_live_request_uses_submitted_area_centre_and_rain_field(self):
        response = io.BytesIO(json.dumps(forecast_payload()).encode("utf-8"))
        with patch("weather.urlopen", return_value=response) as open_url:
            result = fetch_weather(self.area)

        query = parse_qs(urlparse(open_url.call_args.args[0].full_url).query)
        self.assertAlmostEqual(float(query["latitude"][0]), self.area.center[0])
        self.assertAlmostEqual(float(query["longitude"][0]), self.area.center[1])
        self.assertIn("rain_sum", query["daily"][0])
        self.assertIn("temperature_2m_min", query["daily"][0])
        self.assertIn("wind_speed_10m_max", query["daily"][0])
        self.assertIn("precipitation_probability_max", query["daily"][0])
        self.assertIn("relative_humidity_2m_mean", query["daily"][0])
        self.assertEqual(len(result.days), 7)

    def test_optional_microclimate_fields_parsed_and_validated(self):
        payload = forecast_payload()
        payload["daily_units"].update({
            "temperature_2m_min": "°C",
            "wind_speed_10m_max": "km/h",
            "precipitation_probability_max": "%",
            "relative_humidity_2m_mean": "%",
        })
        payload["daily"].update({
            "temperature_2m_min": [4.0, 5.0, 3.0, 1.5, 4.5, 6.0, 5.5],
            "wind_speed_10m_max": [8.5, 16.0, 12.0, 26.5, 9.0, 11.0, 7.5],
            "precipitation_probability_max": [10, 20, 65, 15, None, 30, 5],
            "relative_humidity_2m_mean": [72, 78, 86, 82, 68, 74, 70],
        })
        result = parse_weather(payload, self.area, "https://example.test", self.now)
        self.assertEqual(result.days[3].min_temp_c, 1.5)
        self.assertEqual(result.days[3].wind_speed_max_kmh, 26.5)
        self.assertEqual(result.days[2].rain_probability_pct, 65.0)
        self.assertIsNone(result.days[4].rain_probability_pct)
        self.assertEqual(result.days[2].humidity_mean_pct, 86.0)

        bad_wind = forecast_payload()
        bad_wind["daily_units"]["wind_speed_10m_max"] = "km/h"
        bad_wind["daily"]["wind_speed_10m_max"] = [-1.0, 5, 5, 5, 5, 5, 5]
        with self.assertRaises(WeatherError):
            parse_weather(bad_wind, self.area, "https://example.test", self.now)

        bad_prob = forecast_payload()
        bad_prob["daily_units"]["precipitation_probability_max"] = "%"
        bad_prob["daily"]["precipitation_probability_max"] = [10, 20, 120, 10, 10, 10, 10]
        with self.assertRaises(WeatherError):
            parse_weather(bad_prob, self.area, "https://example.test", self.now)


if __name__ == "__main__":
    unittest.main()
