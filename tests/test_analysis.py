import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from ai import AIError
from analysis import analyze
from cache import CacheStore
from location import SAMPLE_AREA, validate_rectangle
from models import AnalysisRequest, ForecastDay, SatelliteResult, WeatherResult
from satellite import SatelliteError
from weather import WeatherError


NOW = datetime(2026, 10, 30, 10, tzinfo=timezone.utc)


def weather(area=SAMPLE_AREA):
    days = tuple(ForecastDay(date(2026, 10, 30) + timedelta(days=i), 0.0, 30.0, 3.0)
                 for i in range(7))
    return WeatherResult(area, days, "Asia/Kolkata", NOW, "https://example.test/weather")


def satellite(area=SAMPLE_AREA):
    return SatelliteResult(area, "scene-1", NOW, 5.0, "https://example.test/scene",
                           NOW, b"red", b"nir", b"ndvi", 0.42, 0.4, 80.0, None, 4, 4)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = CacheStore(Path(self.directory.name))
        self.request = AnalysisRequest(SAMPLE_AREA, "wheat", "Vegetative")
        self.no_ai = Mock(side_effect=AIError("offline"))

    def test_weather_only_uses_no_satellite_evidence(self):
        outcome = analyze(self.request, self.cache, weather_fetcher=lambda area: weather(area),
                          satellite_fetcher=Mock(side_effect=SatelliteError("offline")),
                          ai_ranker=self.no_ai)
        self.assertIsNotNone(outcome.weather.result)
        self.assertIsNone(outcome.satellite.result)
        self.assertTrue(outcome.suggestions)
        self.assertTrue(all(not item.id.startswith("ndvi") for suggestion in outcome.suggestions
                            for item in suggestion.evidence))
        self.assertIn("Rule-based", outcome.suggestion_source)

    def test_satellite_only_uses_no_weather_evidence(self):
        outcome = analyze(self.request, self.cache, weather_fetcher=Mock(side_effect=WeatherError("offline")),
                          satellite_fetcher=lambda area: satellite(area), ai_ranker=self.no_ai)
        self.assertIsNone(outcome.weather.result)
        self.assertIsNotNone(outcome.satellite.result)
        self.assertTrue(outcome.suggestions)
        self.assertTrue(all(item.id in {"ndvi_mean", "valid_pixels"}
                            for suggestion in outcome.suggestions for item in suggestion.evidence))

    def test_neither_source_has_no_suggestions_or_ai_call(self):
        outcome = analyze(self.request, self.cache,
                          weather_fetcher=Mock(side_effect=WeatherError("offline")),
                          satellite_fetcher=Mock(side_effect=SatelliteError("offline")),
                          ai_ranker=self.no_ai)
        self.assertEqual(outcome.suggestions, ())
        self.assertIsNone(outcome.suggestion_source)
        self.no_ai.assert_not_called()

    def test_failed_live_request_reuses_only_exact_rectangle(self):
        self.cache.save_weather(weather())
        self.cache.save_satellite(satellite())
        fail_weather = Mock(side_effect=WeatherError("offline"))
        fail_satellite = Mock(side_effect=SatelliteError("offline"))
        same = analyze(self.request, self.cache, weather_fetcher=fail_weather,
                       satellite_fetcher=fail_satellite, ai_ranker=self.no_ai)
        self.assertTrue(same.weather.cached and same.satellite.cached)
        self.assertEqual(same.weather.result.fetched_at_utc, NOW)
        other_area = validate_rectangle(47.0, 2.0, 47.004, 2.004)
        other = analyze(AnalysisRequest(other_area, "wheat", "Vegetative"), self.cache,
                        weather_fetcher=fail_weather, satellite_fetcher=fail_satellite,
                        ai_ranker=self.no_ai)
        self.assertIsNone(other.weather.result)
        self.assertIsNone(other.satellite.result)
        self.assertEqual(other.suggestions, ())

    def test_explicit_cache_path_makes_no_live_request(self):
        self.cache.save_weather(weather())
        fetch = Mock(side_effect=AssertionError("must not fetch"))
        outcome = analyze(self.request, self.cache, cached_only=True,
                          weather_fetcher=fetch, satellite_fetcher=fetch, ai_ranker=self.no_ai)
        self.assertTrue(outcome.weather.cached)
        self.assertIsNone(outcome.satellite.result)
        fetch.assert_not_called()

    def test_weather_cache_roundtrip_preserves_microclimate_and_triggers_wind_frost_checks(self):
        days = tuple(
            ForecastDay(
                date(2026, 10, 30) + timedelta(days=i),
                0.0,
                22.0,
                3.0,
                min_temp_c=2.0,
                wind_speed_max_kmh=21.0,
                rain_probability_pct=15.0,
                humidity_mean_pct=65.0,
            )
            for i in range(7)
        )
        rich_weather = WeatherResult(SAMPLE_AREA, days, "Asia/Kolkata", NOW, "https://example.test/weather")
        self.cache.save_weather(rich_weather)
        loaded = self.cache.load_weather(SAMPLE_AREA)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.days[0].min_temp_c, 2.0)
        self.assertEqual(loaded.days[0].wind_speed_max_kmh, 21.0)
        self.assertEqual(loaded.days[0].rain_probability_pct, 15.0)
        self.assertEqual(loaded.days[0].humidity_mean_pct, 65.0)

        outcome = analyze(
            self.request,
            self.cache,
            cached_only=True,
            ai_ranker=self.no_ai,
        )
        rec_ids = {s.candidate.id for s in outcome.suggestions}
        self.assertIn("protect_frost", rec_ids)
        self.assertIn("hold_windy_spray", rec_ids)


if __name__ == "__main__":
    unittest.main()
