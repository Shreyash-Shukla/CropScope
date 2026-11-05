import json
import unittest
from datetime import date, datetime, timedelta, timezone

from analysis import AnalysisOutcome, SourceState
from location import SAMPLE_AREA
from models import AnalysisRequest, ForecastDay, SatelliteResult, WeatherResult
from recommendations import Candidate, Evidence, Suggestion
from reporting import generate_advisory_json, generate_advisory_markdown


NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def sample_outcome(weather_ok=True, satellite_ok=True):
    days = tuple(
        ForecastDay(date(2026, 11, 1) + timedelta(days=i), 2.0 * i, 28.0 + i, 3.5)
        for i in range(7)
    )
    weather_res = WeatherResult(SAMPLE_AREA, days, "Asia/Kolkata", NOW, "https://example.test/weather") if weather_ok else None
    satellite_res = SatelliteResult(
        SAMPLE_AREA, "scene-karnal-123", NOW, 4.5, "https://example.test/scene",
        NOW, b"red", b"nir", b"ndvi", 0.45, 0.42, 92.5, None, 100, 100
    ) if satellite_ok else None

    req = AnalysisRequest(SAMPLE_AREA, "wheat", "Vegetative")
    weather_state = SourceState(weather_res, False, None if weather_ok else "Weather API timeout")
    sat_state = SourceState(satellite_res, False, None if satellite_ok else "No scene found")

    evidence = (Evidence("rain_total", "Seven-day forecast rain: 42.0 mm."),)
    candidate = Candidate("check_drainage", "Check drainage", "Inspect field drainage.", ("rain_total",), 10)
    suggestions = (Suggestion(candidate, evidence),) if (weather_ok or satellite_ok) else ()

    return AnalysisOutcome(
        req, weather_state, sat_state, suggestions,
        "Rule-based fallback" if suggestions else None
    )


class ReportingTests(unittest.TestCase):
    def test_markdown_full_report(self):
        outcome = sample_outcome(weather_ok=True, satellite_ok=True)
        md = generate_advisory_markdown(outcome, generated_at=NOW)

        self.assertIn("# CropScope — Field Advisory Report", md)
        self.assertIn("wheat", md)
        self.assertIn("Vegetative", md)
        self.assertIn("scene-karnal-123", md)
        self.assertIn("Check drainage", md)
        self.assertIn("Decision-Support Boundaries", md)
        self.assertIn("Net Atmospheric Water Balance", md)
        self.assertIn("| Date | Rain (mm) | Max Temp (°C) |", md)

    def test_markdown_partial_sources(self):
        # Weather only
        outcome_w = sample_outcome(weather_ok=True, satellite_ok=False)
        md_w = generate_advisory_markdown(outcome_w, generated_at=NOW)
        self.assertIn("Satellite data unavailable: No scene found", md_w)
        self.assertIn("Seven-Day Agro-Climatic", md_w)

        # Satellite only
        outcome_s = sample_outcome(weather_ok=False, satellite_ok=True)
        md_s = generate_advisory_markdown(outcome_s, generated_at=NOW)
        self.assertIn("Weather data unavailable: Weather API timeout", md_s)
        self.assertIn("Mean NDVI", md_s)

    def test_json_report(self):
        outcome = sample_outcome(weather_ok=True, satellite_ok=True)
        raw_json = generate_advisory_json(outcome, generated_at=NOW)
        data = json.loads(raw_json)

        self.assertEqual(data["crop"], "wheat")
        self.assertEqual(data["growth_stage"], "Vegetative")
        self.assertIn("weather", data)
        self.assertIn("satellite", data)
        self.assertEqual(data["weather"]["favorable_days_count"], 1)
        self.assertEqual(data["satellite"]["scene_id"], "scene-karnal-123")
        self.assertEqual(len(data["suggestions"]), 1)


if __name__ == "__main__":
    unittest.main()
