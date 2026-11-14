import unittest
from datetime import date, datetime, timedelta, timezone

from analysis import AnalysisOutcome, SourceState
from chatbot import build_farmer_dossier, chat_with_kisan_mitra, get_dossier_summary_stats
from location import SAMPLE_AREA
from models import AnalysisRequest, ForecastDay, SatelliteResult, WeatherResult
from recommendations import Candidate, Evidence, Suggestion

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def make_test_outcome(weather_ok=True, satellite_ok=True, rain_override=None, temp_override=None):
    days = []
    for i in range(7):
        r = rain_override if rain_override is not None else 2.0 * i
        t = temp_override if temp_override is not None else (26.0 + i)
        days.append(ForecastDay(date(2026, 11, 1) + timedelta(days=i), r, t, 3.5))

    weather_res = WeatherResult(SAMPLE_AREA, tuple(days), "Asia/Kolkata", NOW, "https://example.test/weather") if weather_ok else None
    satellite_res = (
        SatelliteResult(
            area=SAMPLE_AREA,
            scene_id="scene-karnal-s2",
            acquired_at_utc=NOW,
            scene_cloud_percent=3.2,
            catalog_url="https://example.test/scene",
            fetched_at_utc=NOW,
            red_preview_png=b"red",
            nir_preview_png=b"nir",
            ndvi_png=b"ndvi",
            mean_ndvi=0.58,
            median_ndvi=0.56,
            valid_pixel_percent=95.0,
            quality_message=None,
            width=120,
            height=120,
            mean_savi=0.52,
            canopy_zones={
                "Dense canopy (NDVI >= 0.6)": 45.0,
                "Moderate canopy (0.4-0.6)": 35.0,
                "Sparse / emerging (0.2-0.4)": 15.0,
                "Bare soil (< 0.2)": 5.0,
                "Water / shadow": 0.0,
            },
        )
        if satellite_ok
        else None
    )

    req = AnalysisRequest(SAMPLE_AREA, "Wheat", "Vegetative")
    w_state = SourceState(weather_res, False, None if weather_ok else "Weather API timeout")
    s_state = SourceState(satellite_res, False, None if satellite_ok else "No Sentinel-2 scene found")

    evidence = (Evidence("rain_total", "Seven-day forecast rain: 42.0 mm."),)
    candidate = Candidate("check_irrigation", "Evaluate irrigation", "Adjust irrigation timing.", ("rain_total",), 10)
    suggestions = (Suggestion(candidate, evidence),) if (weather_ok or satellite_ok) else ()

    return AnalysisOutcome(req, w_state, s_state, suggestions, "Verified AI Ranking" if suggestions else None)


class ChatbotDossierTests(unittest.TestCase):
    def test_get_dossier_summary_stats_full(self):
        outcome = make_test_outcome(weather_ok=True, satellite_ok=True)
        stats = get_dossier_summary_stats(outcome)

        self.assertEqual(stats["crop"], "Wheat")
        self.assertEqual(stats["growth_stage"], "Vegetative")
        self.assertTrue(stats["weather_available"])
        self.assertTrue(stats["satellite_available"])
        self.assertAlmostEqual(stats["total_rain_7d_mm"], 42.0)
        self.assertAlmostEqual(stats["total_et0_7d_mm"], 24.5)
        self.assertAlmostEqual(stats["net_water_balance_mm"], 17.5)
        self.assertEqual(stats["mean_ndvi"], 0.58)
        self.assertEqual(stats["mean_savi"], 0.52)
        self.assertEqual(stats["valid_pixels_pct"], 95.0)
        self.assertIn("Dense canopy (NDVI >= 0.6)", stats["canopy_zones"])
        self.assertEqual(stats["suggestions_count"], 1)

    def test_build_farmer_dossier_full(self):
        outcome = make_test_outcome(weather_ok=True, satellite_ok=True)
        dossier = build_farmer_dossier(outcome, lang="en")

        self.assertIn("=== CROP & FIELD INTELLIGENCE GROUND-TRUTH DOSSIER ===", dossier)
        self.assertIn("Target Crop: Wheat", dossier)
        self.assertIn("Vegetative", dossier)
        self.assertIn("## 1. FIELD GEOMETRY & LOCATION", dossier)
        self.assertIn("## 2. SEVEN-DAY AGRO-CLIMATIC & WATER BALANCE FORECAST", dossier)
        self.assertIn("| Date | Max Temp (°C) | Rain (mm) | ET₀ (mm) | Net Balance (mm) |", dossier)
        self.assertIn("## 3. SENTINEL-2 SATELLITE MULTISPECTRAL CANOPY HEALTH", dossier)
        self.assertIn("scene-karnal-s2", dossier)
        self.assertIn("0.58", dossier)
        self.assertIn("Dense canopy (NDVI >= 0.6): 45.0%", dossier)
        self.assertIn("## 4. PRIORITIZED FIELD ACTION CHECKS", dossier)
        self.assertIn("Evaluate irrigation", dossier)
        self.assertIn("=== END OF GROUND-TRUTH DOSSIER ===", dossier)

    def test_dossier_partial_weather_only(self):
        outcome = make_test_outcome(weather_ok=True, satellite_ok=False)
        dossier = build_farmer_dossier(outcome, lang="en")

        self.assertIn("## 2. SEVEN-DAY AGRO-CLIMATIC", dossier)
        self.assertIn("Satellite data unavailable (No Sentinel-2 scene found)", dossier)

    def test_dossier_partial_satellite_only(self):
        outcome = make_test_outcome(weather_ok=False, satellite_ok=True)
        dossier = build_farmer_dossier(outcome, lang="en")

        self.assertIn("Weather unavailable (Weather API timeout)", dossier)
        self.assertIn("0.58", dossier)
        self.assertIn("scene-karnal-s2", dossier)

    def test_safe_to_spray_flag(self):
        # Case 1: Heavy imminent rain (e.g. 10mm on Day 1) -> Unsafe to spray
        outcome_rainy = make_test_outcome(weather_ok=True, rain_override=6.0)
        stats_rainy = get_dossier_summary_stats(outcome_rainy)
        self.assertFalse(stats_rainy["safe_to_spray_next_48h"])
        dossier_rainy = build_farmer_dossier(outcome_rainy)
        self.assertIn("UNFAVORABLE / CAUTION", dossier_rainy)

        # Case 2: Clear, cool weather (0mm rain, 25°C) -> Favorable to spray
        outcome_clear = make_test_outcome(weather_ok=True, rain_override=0.0, temp_override=25.0)
        stats_clear = get_dossier_summary_stats(outcome_clear)
        self.assertTrue(stats_clear["safe_to_spray_next_48h"])
        dossier_clear = build_farmer_dossier(outcome_clear)
        self.assertIn("Spray Safety Window Next 48h: FAVORABLE", dossier_clear)


class ChatbotEngineTests(unittest.TestCase):
    def setUp(self):
        self.outcome = make_test_outcome(weather_ok=True, satellite_ok=True)
        self.stats = get_dossier_summary_stats(self.outcome)
        self.dossier = build_farmer_dossier(self.outcome)

    def test_fallback_rain_query(self):
        resp_en = chat_with_kisan_mitra(
            [{"role": "user", "content": "Will it rain this week?"}],
            self.dossier,
            self.stats,
            lang="en",
            api_key="",
        )
        self.assertIn("Weather & Rainfall Outlook", resp_en)
        self.assertIn("42.0 mm", resp_en)

        resp_hi = chat_with_kisan_mitra(
            [{"role": "user", "content": "क्या बारिश होगी?"}],
            self.dossier,
            self.stats,
            lang="hi",
            api_key="",
        )
        self.assertIn("मौसम व वर्षा रिपोर्ट", resp_hi)
        self.assertIn("मिमी", resp_hi)

    def test_fallback_spray_query(self):
        # Rainy scenario -> caution
        rainy_outcome = make_test_outcome(weather_ok=True, rain_override=5.0)
        rainy_stats = get_dossier_summary_stats(rainy_outcome)
        resp_caution = chat_with_kisan_mitra(
            [{"role": "user", "content": "Can I spray pesticide tomorrow?"}],
            self.dossier,
            rainy_stats,
            lang="en",
            api_key="",
        )
        self.assertIn("UNFAVORABLE", resp_caution)
        self.assertIn("Hold chemical spraying", resp_caution)

        # Dry scenario -> favorable
        dry_outcome = make_test_outcome(weather_ok=True, rain_override=0.0, temp_override=24.0)
        dry_stats = get_dossier_summary_stats(dry_outcome)
        resp_favorable = chat_with_kisan_mitra(
            [{"role": "user", "content": "Can I spray fertilizer tomorrow?"}],
            self.dossier,
            dry_stats,
            lang="en",
            api_key="",
        )
        self.assertIn("Favorable window", resp_favorable)

    def test_fallback_ndvi_canopy_query(self):
        resp = chat_with_kisan_mitra(
            [{"role": "user", "content": "How is my crop NDVI and greenness?"}],
            self.dossier,
            self.stats,
            lang="en",
            api_key="",
        )
        self.assertIn("Satellite Vegetation Health", resp)
        self.assertIn("0.58", resp)

    def test_chat_with_gemini_client_mock(self):
        from unittest.mock import MagicMock, patch

        mock_resp = MagicMock()
        mock_resp.text = "राम राम किसान भाई! आपकी गेहूं की फसल हरी-भरी है और मौसम अनुकूल है।"

        with patch("chatbot.genai.Client") as mock_client_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.models.generate_content.return_value = mock_resp
            mock_client_cls.return_value.__enter__.return_value = mock_client_instance

            res = chat_with_kisan_mitra(
                [{"role": "user", "content": "नमस्ते, मेरी फसल कैसी है?"}],
                self.dossier,
                self.stats,
                lang="hi",
                api_key="mock-test-key",
            )
            self.assertEqual(res, mock_resp.text)
            mock_client_instance.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
