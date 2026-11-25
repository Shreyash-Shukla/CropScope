import unittest
from datetime import date, timedelta

from agronomy import (
    COMMON_CROPS,
    GROWTH_STAGE_GUIDANCE,
    AgroClimaticSummary,
    CropWaterPlan,
    OperationalWindows,
    WeatherAlert,
    compute_agro_climatic_summary,
    compute_crop_water_plan,
    evaluate_fieldwork_suitability,
    evaluate_operational_windows,
    generate_weather_alerts,
    get_crop_coefficient,
    get_growth_stage_guidance,
    summarize_canopy_health,
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

    def test_summarize_canopy_health(self):
        dense_zones = {
            "Dense Canopy (>0.60)": 60.0,
            "Moderate Canopy (0.35-0.60)": 25.0,
            "Sparse / Emerging (0.20-0.35)": 10.0,
            "Bare Soil / Non-Vegetated (0.00-0.20)": 5.0,
            "Water / Negative Index (<0.00)": 0.0,
        }
        res_dense = summarize_canopy_health(dense_zones)
        self.assertIn("High canopy density", res_dense)
        self.assertIn("85.0%", res_dense)

        bare_zones = {
            "Dense Canopy (>0.60)": 0.0,
            "Moderate Canopy (0.35-0.60)": 10.0,
            "Sparse / Emerging (0.20-0.35)": 20.0,
            "Bare Soil / Non-Vegetated (0.00-0.20)": 70.0,
            "Water / Negative Index (<0.00)": 0.0,
        }
        res_bare = summarize_canopy_health(bare_zones)
        self.assertIn("Low canopy cover", res_bare)

        self.assertEqual(summarize_canopy_health(None), "")
        self.assertEqual(summarize_canopy_health({}), "")

    def test_generate_weather_alerts(self):
        # 1. Extreme heat + heavy rain + surplus
        days_extreme = (
            ForecastDay(date(2026, 11, 1), 15.0, 39.0, 3.0),
            ForecastDay(date(2026, 11, 2), 12.0, 30.0, 3.0),
            ForecastDay(date(2026, 11, 3), 5.0, 28.0, 3.0),
            ForecastDay(date(2026, 11, 4), 0.0, 26.0, 3.0),
            ForecastDay(date(2026, 11, 5), 0.0, 25.0, 3.0),
            ForecastDay(date(2026, 11, 6), 0.0, 25.0, 3.0),
            ForecastDay(date(2026, 11, 7), 0.0, 25.0, 3.0),
        )
        weather_extreme = WeatherResult(SAMPLE_AREA, days_extreme, "UTC", date(2026, 11, 1), "http://test")
        alerts_extreme = generate_weather_alerts(weather_extreme)

        categories = [a.category for a in alerts_extreme]
        self.assertIn("Rain", categories)
        self.assertIn("Heat", categories)
        danger_alerts = [a for a in alerts_extreme if a.level == "danger"]
        self.assertGreaterEqual(len(danger_alerts), 1)

        # 2. Calm / stable weather with good spray window
        days_calm = tuple(
            ForecastDay(date(2026, 11, 1) + timedelta(days=i), 0.0, 24.0, 2.5)
            for i in range(7)
        )
        weather_calm = WeatherResult(SAMPLE_AREA, days_calm, "UTC", date(2026, 11, 1), "http://test")
        alerts_calm = generate_weather_alerts(weather_calm)
        self.assertTrue(any(a.category == "Spraying" and a.level == "success" for a in alerts_calm))

        # 3. Empty weather days
        weather_empty = WeatherResult(SAMPLE_AREA, (), "UTC", date(2026, 11, 1), "http://test")
        self.assertEqual(generate_weather_alerts(weather_empty), ())

    def test_wind_frost_humidity_and_gdd_enhancements(self):
        # Wind & frost suitability checks
        suit_wind_rest, _ = evaluate_fieldwork_suitability(
            ForecastDay(date(2026, 11, 1), 0.0, 24.0, 3.0, min_temp_c=8.0, wind_speed_max_kmh=27.0)
        )
        self.assertEqual(suit_wind_rest, "Restricted: Wind")

        suit_frost, _ = evaluate_fieldwork_suitability(
            ForecastDay(date(2026, 11, 1), 0.0, 18.0, 2.0, min_temp_c=1.5, wind_speed_max_kmh=8.0)
        )
        self.assertEqual(suit_frost, "Caution: Frost")

        suit_wind_caut, _ = evaluate_fieldwork_suitability(
            ForecastDay(date(2026, 11, 1), 0.0, 24.0, 3.0, min_temp_c=10.0, wind_speed_max_kmh=18.0)
        )
        self.assertEqual(suit_wind_caut, "Caution: Wind")

        # 7-day summary with GDD, wind, min temp, humidity & spray exclusion for wind
        days = (
            ForecastDay(date(2026, 11, 1), 0.0, 26.0, 3.0, min_temp_c=14.0, wind_speed_max_kmh=10.0, humidity_mean_pct=84.0),
            ForecastDay(date(2026, 11, 2), 0.0, 26.0, 3.0, min_temp_c=1.0, wind_speed_max_kmh=26.0, humidity_mean_pct=82.0),
            ForecastDay(date(2026, 11, 3), 0.0, 24.0, 3.0, min_temp_c=12.0, wind_speed_max_kmh=12.0, humidity_mean_pct=85.0),
            ForecastDay(date(2026, 11, 4), 0.0, 24.0, 3.0, min_temp_c=12.0, wind_speed_max_kmh=11.0, humidity_mean_pct=70.0),
        )
        weather = WeatherResult(SAMPLE_AREA, days, "UTC", date(2026, 11, 1), "http://test")
        summary = compute_agro_climatic_summary(weather)
        self.assertEqual(summary.min_temp_c, 1.0)
        self.assertEqual(summary.max_wind_kmh, 26.0)
        self.assertAlmostEqual(summary.avg_humidity_pct, 80.2, places=1)
        # Day1 GDD=(26+14)/2-10=10, Day2=(26+1)/2-10=3.5, Day3=8, Day4=8 => 29.5
        self.assertAlmostEqual(summary.total_gdd_base10, 29.5, places=1)

        windows = evaluate_operational_windows(weather)
        # Day 2 excluded due to wind 26 km/h
        self.assertEqual(len(windows.spraying_favorable_days), 3)

        alerts = generate_weather_alerts(weather)
        categories = {a.category for a in alerts}
        self.assertIn("Frost", categories)
        self.assertIn("Wind", categories)
        self.assertIn("Humidity", categories)

    def test_crop_coefficient_and_water_plan(self):
        kc_rice, src_rice = get_crop_coefficient("Rice / Paddy", "Flowering")
        self.assertEqual(kc_rice, 1.20)
        self.assertIn("Rice / Paddy", src_rice)

        kc_alias, src_alias = get_crop_coefficient("Winter wheat variety", "Seedling")
        self.assertEqual(kc_alias, 0.40)
        self.assertIn("Wheat", src_alias)

        kc_custom, src_custom = get_crop_coefficient("Dragonfruit", "Vegetative")
        self.assertEqual(kc_custom, 0.80)
        self.assertIn("Generic", src_custom)

        # 7 days with 0 rain, 4.0 mm ET0 -> total ET0 = 28 mm; Wheat Flowering Kc = 1.15 -> ETc = 32.2 mm
        days = tuple(
            ForecastDay(date(2026, 11, 1) + timedelta(days=i), 0.0, 30.0, 4.0)
            for i in range(7)
        )
        weather = WeatherResult(SAMPLE_AREA, days, "UTC", date(2026, 11, 1), "http://test")
        plan = compute_crop_water_plan(weather, "Wheat", "Flowering")
        self.assertIsInstance(plan, CropWaterPlan)
        self.assertEqual(plan.kc, 1.15)
        self.assertAlmostEqual(plan.total_etc_mm, 32.2, places=2)
        self.assertAlmostEqual(plan.crop_net_balance_mm, -32.2, places=2)
        self.assertAlmostEqual(plan.estimated_deficit_mm, 32.2, places=2)
        self.assertGreater(plan.deficit_m3, 0.0)
        self.assertGreater(plan.deficit_liters_per_acre, 120_000.0)
        self.assertIn("Deficit", plan.status_label)


if __name__ == "__main__":
    unittest.main()

