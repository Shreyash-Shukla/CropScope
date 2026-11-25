import json
import unittest
from datetime import date, datetime, timedelta, timezone

from analysis import AnalysisOutcome, SourceState
from location import SAMPLE_AREA
from models import AnalysisRequest, ForecastDay, SatelliteResult, WeatherResult
from recommendations import Candidate, Evidence, Suggestion
from reporting import (
    advisory_filename_base,
    build_whatsapp_share_url,
    generate_advisory_html,
    generate_advisory_json,
    generate_advisory_markdown,
    generate_whatsapp_brief,
)


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
        self.assertIn("ha", md)
        self.assertIn("ac", md)
        self.assertIn("Check drainage", md)
        self.assertIn("Decision-Support Boundaries", md)
        self.assertIn("Net Atmospheric Water Balance", md)
        self.assertIn("Field Operations Windows", md)
        self.assertIn("Operational Weather Alerts", md)
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
        self.assertIn("growth_stage_guidance", data)
        self.assertIn("area_ha", data["area"])
        self.assertIn("area_acres", data["area"])
        self.assertIn("weather", data)
        self.assertIn("satellite", data)
        self.assertEqual(data["weather"]["favorable_days_count"], 1)
        self.assertIn("crop_water_plan", data["weather"])
        self.assertAlmostEqual(data["weather"]["crop_water_plan"]["kc"], 0.85)
        self.assertIn("operational_windows", data["weather"])
        self.assertIn("alerts", data["weather"])
        self.assertEqual(data["satellite"]["scene_id"], "scene-karnal-123")
        self.assertEqual(len(data["suggestions"]), 1)

    def test_advisory_filename_sanitization(self):
        # Standard crop name
        outcome = sample_outcome()
        base = advisory_filename_base(outcome)
        self.assertTrue(base.startswith("cropscope_advisory_wheat_"))
        self.assertNotIn("/", base)
        self.assertNotIn("\\", base)

        # Crop name with slashes and special characters
        req_special = AnalysisRequest(SAMPLE_AREA, "Wheat / Barley (Winter #1)", "Vegetative")
        outcome_special = AnalysisOutcome(
            req_special, outcome.weather, outcome.satellite, outcome.suggestions, outcome.suggestion_source
        )
        base_special = advisory_filename_base(outcome_special)
        self.assertTrue(base_special.startswith("cropscope_advisory_wheat_barley_winter_1_"))
        self.assertNotIn("/", base_special)
        self.assertNotIn("\\", base_special)
        self.assertNotIn("(", base_special)
        self.assertNotIn(")", base_special)
        self.assertNotIn("#", base_special)

    def test_reports_include_microclimate_when_present(self):
        days = tuple(
            ForecastDay(
                date(2026, 11, 1) + timedelta(days=i),
                0.0,
                26.0,
                3.0,
                min_temp_c=8.0 + i,
                wind_speed_max_kmh=18.5,
                rain_probability_pct=20.0,
                humidity_mean_pct=75.0,
            )
            for i in range(7)
        )
        weather_res = WeatherResult(SAMPLE_AREA, days, "Asia/Kolkata", NOW, "https://example.test/weather")
        base = sample_outcome(weather_ok=True, satellite_ok=False)
        outcome = AnalysisOutcome(
            base.request,
            SourceState(weather_res, False, None),
            base.satellite,
            base.suggestions,
            base.suggestion_source,
        )
        md = generate_advisory_markdown(outcome, generated_at=NOW)
        self.assertIn("Min Temp (°C)", md)
        self.assertIn("Wind (km/h)", md)
        self.assertIn("GDD Base 10°C", md)

        data = json.loads(generate_advisory_json(outcome, generated_at=NOW))
        self.assertEqual(data["weather"]["max_wind_kmh"], 18.5)
        self.assertEqual(data["weather"]["min_temp_c"], 8.0)
        self.assertIsNotNone(data["weather"]["total_gdd_base10"])
        self.assertEqual(data["weather"]["days"][0]["wind_speed_max_kmh"], 18.5)

    def test_reports_include_spatial_uniformity_and_quadrants(self):
        base = sample_outcome(weather_ok=False, satellite_ok=True)
        sat = SatelliteResult(
            SAMPLE_AREA, "scene-quad", NOW, 2.0, "https://example.test/scene",
            NOW, b"red", b"nir", b"ndvi", 0.55, 0.54, 96.0, None, 20, 20,
            uniformity_score_pct=62.5,
            ndvi_std=0.1875,
            quadrant_stats={
                "North-West": {"mean_ndvi": 0.68, "low_vigor_pct": 5.0, "valid_pct": 100.0},
                "South-East": {"mean_ndvi": 0.30, "low_vigor_pct": 55.0, "valid_pct": 100.0},
            },
        )
        outcome = AnalysisOutcome(base.request, base.weather, SourceState(sat, False, None), (), None)
        md = generate_advisory_markdown(outcome, generated_at=NOW)
        self.assertIn("Field Canopy Uniformity", md)
        self.assertIn("62.5%", md)
        self.assertIn("South-East", md)

        data = json.loads(generate_advisory_json(outcome, generated_at=NOW))
        self.assertEqual(data["satellite"]["uniformity_score_pct"], 62.5)
        self.assertIn("South-East", data["satellite"]["quadrant_stats"])

    def test_whatsapp_brief_and_share_url(self):
        outcome = sample_outcome(weather_ok=True, satellite_ok=True)
        brief_en = generate_whatsapp_brief(outcome, lang="en", generated_at=NOW)
        self.assertIn("*CropScope Field Brief*", brief_en)
        self.assertIn("wheat", brief_en)
        self.assertIn("Mean NDVI 0.450", brief_en)
        share_url = build_whatsapp_share_url(brief_en)
        self.assertTrue(share_url.startswith("https://wa.me/?text="))

        brief_hi = generate_whatsapp_brief(outcome, lang="hi", generated_at=NOW)
        self.assertIn("CropScope खेत सारांश", brief_hi)

        brief_pa = generate_whatsapp_brief(outcome, lang="pa", generated_at=NOW)
        self.assertIn("CropScope ਖੇਤ ਰਿਪੋਰਟ", brief_pa)

    def test_printable_html_report_escapes_inputs_and_embeds_images(self):
        base = sample_outcome(weather_ok=True, satellite_ok=True)
        xss_req = AnalysisRequest(SAMPLE_AREA, "<script>alert(1)</script>", "Vegetative")
        sat_with_tci = SatelliteResult(
            SAMPLE_AREA, "scene-html", NOW, 1.5, "https://example.test/scene",
            NOW, b"red", b"nir", b"ndvi_png_bytes", 0.52, 0.50, 95.0, None, 10, 10,
            true_color_png=b"tci_png_bytes",
        )
        outcome = AnalysisOutcome(xss_req, base.weather, SourceState(sat_with_tci, False, None), base.suggestions, base.suggestion_source)
        html_doc = generate_advisory_html(outcome, generated_at=NOW)
        self.assertIn("<!DOCTYPE html>", html_doc)
        self.assertIn("@media print", html_doc)
        self.assertIn("data:image/png;base64,", html_doc)
        self.assertNotIn("<script>alert(1)</script>", html_doc)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_doc)


if __name__ == "__main__":
    unittest.main()
