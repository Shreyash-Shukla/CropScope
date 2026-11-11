import unittest
from datetime import date, timedelta

from agronomy import (
    COMMON_CROPS,
    GROWTH_STAGE_GUIDANCE,
    AgroClimaticSummary,
    OperationalWindows,
    compute_agro_climatic_summary,
    evaluate_fieldwork_suitability,
    evaluate_operational_windows,
    get_growth_stage_guidance,
)
from location import SAMPLE_AREA
from models import ForecastDay, WeatherResult


class AgronomyTests(unittest.TestCase):
    def test_suitability_classification(self):
        # Heavy rain
        suit, reason = evaluate_fieldwork_suitability(ForecastDay(date(2026, 11, 1), 12.0, 25.0, 3.0))
        self.assertEqual(suit, "Restricted: Rain")
        self.assertIn("runoff", reason.lower())

        # Extreme heat
        suit, reason = evaluate_fieldwork_suitability(ForecastDay(date(2026, 11, 1), 0.0, 39.0, 6.0))
        self.assertEqual(suit, "Restricted: Heat")
        self.assertIn("thermal stress", reason.lower())

        # Moderate rain
        suit, reason = evaluate_fieldwork_suitability(ForecastDay(date(2026, 11, 1), 4.5, 26.0, 3.0))
        self.assertEqual(suit, "Caution: Wet")
        self.assertIn("wash off", reason.lower())

        # Elevated temp
        suit, reason = evaluate_fieldwork_suitability(ForecastDay(date(2026, 11, 1), 0.0, 34.0, 4.5))
        self.assertEqual(suit, "Caution: Heat")
        self.assertIn("volatilization", reason.lower())

        # Favorable
        suit, reason = evaluate_fieldwork_suitability(ForecastDay(date(2026, 11, 1), 0.5, 27.0, 3.5))
        self.assertEqual(suit, "Favorable")
        self.assertIn("favorable", reason.lower())

    def test_agro_climatic_summary_deficit(self):
        days = tuple(
            ForecastDay(date(2026, 11, 1) + timedelta(days=i), 0.0, 30.0, 4.0)
            for i in range(7)
        )
        weather = WeatherResult(SAMPLE_AREA, days, "UTC", date(2026, 11, 1), "http://test")
        summary = compute_agro_climatic_summary(weather)

        self.assertIsInstance(summary, AgroClimaticSummary)
        self.assertEqual(summary.total_rain_mm, 0.0)
        self.assertEqual(summary.total_et0_mm, 28.0)
        self.assertEqual(summary.net_balance_mm, -28.0)
        self.assertIn("Deficit", summary.status_label)
        self.assertEqual(summary.favorable_days_count, 7)
        self.assertEqual(len(summary.days), 7)

    def test_agro_climatic_summary_surplus(self):
        days = tuple(
            ForecastDay(date(2026, 11, 1) + timedelta(days=i), 15.0, 22.0, 2.0)
            for i in range(7)
        )
        weather = WeatherResult(SAMPLE_AREA, days, "UTC", date(2026, 11, 1), "http://test")
        summary = compute_agro_climatic_summary(weather)

        self.assertEqual(summary.total_rain_mm, 105.0)
        self.assertEqual(summary.total_et0_mm, 14.0)
        self.assertEqual(summary.net_balance_mm, 91.0)
        self.assertIn("Surplus", summary.status_label)
        self.assertEqual(summary.favorable_days_count, 0)  # Rain >= 10 on all days


    def test_evaluate_operational_windows(self):
        days = (
            ForecastDay(date(2026, 11, 1), 0.0, 26.0, 3.0),   # optimal spraying, machinery, scouting
            ForecastDay(date(2026, 11, 2), 3.0, 28.0, 3.2),   # caution wet: machinery & scouting ok, no spray
            ForecastDay(date(2026, 11, 3), 15.0, 24.0, 2.0),  # heavy rain: none
            ForecastDay(date(2026, 11, 4), 0.0, 34.0, 4.0),   # heat: machinery & scouting ok, no spray
        )
        weather = WeatherResult(SAMPLE_AREA, days, "UTC", date(2026, 11, 1), "http://test")
        windows = evaluate_operational_windows(weather)

        self.assertIsInstance(windows, OperationalWindows)
        self.assertEqual(len(windows.spraying_favorable_days), 1)
        self.assertEqual(len(windows.machinery_accessible_days), 3)
        self.assertEqual(len(windows.scouting_recommended_days), 3)

    def test_common_crops_and_growth_stage_guidance(self):
        self.assertIn("Wheat", COMMON_CROPS)
        self.assertIn("Rice / Paddy", COMMON_CROPS)
        self.assertIn("Corn / Maize", COMMON_CROPS)
        self.assertGreaterEqual(len(COMMON_CROPS), 8)

        self.assertIn("Seedling", GROWTH_STAGE_GUIDANCE)
        self.assertIn("Vegetative", GROWTH_STAGE_GUIDANCE)
        self.assertIn("Flowering", GROWTH_STAGE_GUIDANCE)
        self.assertIn("Maturity", GROWTH_STAGE_GUIDANCE)

        flowering_guide = get_growth_stage_guidance("Flowering")
        self.assertIn("pollination", flowering_guide.lower())
        self.assertEqual(get_growth_stage_guidance(None), "")
        self.assertIn("General", get_growth_stage_guidance("UnknownCustomStage"))


if __name__ == "__main__":
    unittest.main()

