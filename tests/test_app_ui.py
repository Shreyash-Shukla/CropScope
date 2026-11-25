import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


class AppUITests(unittest.TestCase):
    def test_paste_coordinates_updates_number_inputs(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        at.radio[0].set_value("Enter coordinates").run()
        at.text_input(key="coord_paste_input").input("48.8566, 2.3522").run()
        self.assertAlmostEqual(at.number_input(key="coord_center_lat").value, 48.8566, places=4)
        self.assertAlmostEqual(at.number_input(key="coord_center_lon").value, 2.3522, places=4)

    def test_paste_four_coordinates_boundary_updates_inputs(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        at.radio[0].set_value("Enter coordinates").run()
        at.radio(key="coord_entry_type").set_value("Four-Corner Boundary (N/S/W/E)").run()
        at.text_input(key="coord_boundary_paste_input").input("48.252, 48.248, 1.698, 1.702").run()
        self.assertAlmostEqual(at.number_input(key="coord_north").value, 48.252, places=4)
        self.assertAlmostEqual(at.number_input(key="coord_south").value, 48.248, places=4)
        self.assertAlmostEqual(at.number_input(key="coord_west").value, 1.698, places=4)
        self.assertAlmostEqual(at.number_input(key="coord_east").value, 1.702, places=4)

    def test_search_location_suggestions_pill_selection(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        at.radio[0].set_value("Search location").run()
        self.assertGreater(len(at.pills), 0)
        at.pills[0].set_value("🌾 Karnal, India").run()
        self.assertEqual(at.text_input(key="location_search_input").value, "Karnal, Haryana, India")

    def test_header_renders(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        header_markdown = [m.value for m in at.markdown if 'data-testid="cropscope-header"' in m.value]
        self.assertEqual(len(header_markdown), 1)
        self.assertIn("CROPSCOPE", header_markdown[0].upper())
        self.assertIn("SENTINEL-2", header_markdown[0])
        self.assertIn("OPEN-METEO", header_markdown[0])

    def test_footer_renders(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        footer_markdown = [m.value for m in at.markdown if 'data-testid="cropscope-footer"' in m.value]
        self.assertEqual(len(footer_markdown), 1)
        self.assertIn("CROPSCOPE", footer_markdown[0].upper())
        self.assertIn("DATA PROVENANCE", footer_markdown[0].upper())
        self.assertIn("HONEST SCIENTIFIC BOUNDARY", footer_markdown[0].upper())

    def test_theme_selector_toggles_mode(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        theme_sel = at.selectbox(key="theme_selector")
        self.assertEqual(theme_sel.value, "Dark")
        self.assertEqual(at.session_state["theme"], "Dark")
        theme_sel.select("Light").run()
        self.assertEqual(at.session_state["theme"], "Light")

    def test_dropdown_options_available_in_both_themes(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        crop_sel = at.selectbox(key="crop_select")
        self.assertGreater(len(crop_sel.options), 1)
        at.selectbox(key="theme_selector").select("Light").run()
        self.assertEqual(at.session_state["theme"], "Light")
        crop_sel = at.selectbox(key="crop_select")
        self.assertGreater(len(crop_sel.options), 1)

    def test_language_selector_updates_session_state(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        lang_sel = at.selectbox(key="language_selector")
        self.assertEqual(lang_sel.value, "English")
        self.assertEqual(at.session_state["selected_language"], "en")
        lang_sel.select("हिन्दी (Hindi)").run()
        self.assertEqual(at.session_state["selected_language"], "hi")
        # Verify UI labels updated to Hindi
        from i18n import t
        self.assertEqual(at.radio[0].label, t("choose_area_mode", "hi"))
        self.assertEqual(at.selectbox(key="crop_select").label, t("crop_label", "hi"))
        self.assertEqual(at.button[0].label, t("btn_analyze_live", "hi"))
        self.assertEqual(at.button[1].label, t("btn_use_saved", "hi"))

    def test_kisan_mitra_chat_interaction(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.run()
        at.radio[0].set_value("Use sample preset").run()
        at.selectbox(key="crop_select").select("Wheat").run()
        at.selectbox(key="growth_stage_select").select("Vegetative").run()
        at.button[1].click().run()
        self.assertIn("kisan_chat_messages", at.session_state)
        pills = at.pills(key="kisan_quick_pills")
        self.assertIsNotNone(pills)
        self.assertGreater(len(pills.options), 0)
        at.chat_input(key="kisan_chat_input").set_value("Will it rain?").run()
        self.assertGreaterEqual(len(at.session_state["kisan_chat_messages"]), 2)
        self.assertEqual(at.session_state["kisan_chat_messages"][0]["role"], "user")
        self.assertEqual(at.session_state["kisan_chat_messages"][0]["content"], "Will it rain?")
        self.assertEqual(at.session_state["kisan_chat_messages"][1]["role"], "assistant")
        self.assertTrue(len(at.session_state["kisan_chat_messages"][1]["content"]) > 0)

    def test_chat_and_pills_in_light_mode(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.run()
        at.selectbox(key="theme_selector").select("Light").run()
        self.assertEqual(at.session_state["theme"], "Light")
        at.radio[0].set_value("Use sample preset").run()
        at.selectbox(key="crop_select").select("Wheat").run()
        at.selectbox(key="growth_stage_select").select("Vegetative").run()
        at.button[1].click().run()
        self.assertIn("kisan_chat_messages", at.session_state)
        pills = at.pills(key="kisan_quick_pills")
        self.assertIsNotNone(pills)
        self.assertGreater(len(pills.options), 0)
        at.chat_input(key="kisan_chat_input").set_value("How is canopy health?").run()
        self.assertGreaterEqual(len(at.session_state["kisan_chat_messages"]), 2)

    def test_orbit_to_field_hybrid_inspector(self):
        at = AppTest.from_file(APP_PATH, default_timeout=25)
        at.run()
        at.radio[0].set_value("Use sample preset").run()
        field_anchors = [m.value for m in at.markdown if "field-inspector-section" in m.value]
        self.assertEqual(len(field_anchors), 1)
        expanders = [e.label for e in at.expander if "SUB-METER OPTICAL FIELD INSPECTOR" in e.label]
        self.assertEqual(len(expanders), 1)

    def test_expander_styling_rules(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        style_markdowns = [m.value for m in at.markdown if "<style>" in m.value]
        combined_css = " ".join(style_markdowns)
        self.assertIn('div[data-testid="stExpander"] summary', combined_css)
        self.assertIn('background-color: var(--ink-2)', combined_css)
        self.assertIn('border-bottom: 1px solid var(--line)', combined_css)

    def test_code_block_and_copy_toolbar_styling_rules(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        style_markdowns = [m.value for m in at.markdown if "<style>" in m.value]
        combined_css = " ".join(style_markdowns)
        self.assertIn('div[data-testid="stCode"]', combined_css)
        self.assertIn('div[data-testid="stCode"] button', combined_css)
        self.assertIn('div[data-testid="stElementToolbarButtonContainer"]', combined_css)
        self.assertIn('button[kind="elementToolbar"]', combined_css)
        self.assertIn('fill: var(--bone)', combined_css)
        self.assertIn('div[data-testid="stCode"] [data-testid="stTooltipHoverTarget"]', combined_css)
        self.assertIn('div[data-testid="stCode"] [data-testid="stTooltipContent"]', combined_css)

    def test_auth_drawer_toggle_cycle(self):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        self.assertFalse(at.exception)
        # Flip toggle on to open drawer
        at.toggle(key="toggle_farmer_account").set_value(True).run()
        self.assertFalse(at.exception)
        self.assertIsNotNone(at.button(key="btn_submit_login"))
        # Flip toggle off to close drawer
        at.toggle(key="toggle_farmer_account").set_value(False).run()
        self.assertFalse(at.exception)

    def test_rich_microclimate_forecast_metrics_render(self):
        from datetime import date, datetime, timedelta, timezone
        from analysis import AnalysisOutcome, SourceState
        from location import SAMPLE_AREA
        from models import AnalysisRequest, ForecastDay, WeatherResult

        now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        days = tuple(
            ForecastDay(
                date(2026, 11, 1) + timedelta(days=i),
                0.0,
                25.0 + i,
                3.0,
                min_temp_c=6.0 + i,
                wind_speed_max_kmh=18.0,
                rain_probability_pct=15.0,
                humidity_mean_pct=78.0,
            )
            for i in range(7)
        )
        req = AnalysisRequest(SAMPLE_AREA, "Wheat", "Vegetative")
        outcome = AnalysisOutcome(
            req,
            SourceState(WeatherResult(SAMPLE_AREA, days, "Asia/Kolkata", now, "https://example.test"), False, None),
            SourceState(None, False, "No scene"),
            (),
            None,
        )
        at = AppTest.from_file(APP_PATH, default_timeout=20)
        at.run()
        at.radio[0].set_value("Use sample preset")
        at.session_state["analysis_request"] = req
        at.session_state["analysis_outcome"] = outcome
        at.run()
        self.assertFalse(at.exception)
        metric_labels = {m.label for m in at.metric}
        self.assertIn("Lowest min temp", metric_labels)
        self.assertIn("Peak wind speed", metric_labels)
        self.assertIn("Mean humidity", metric_labels)
        self.assertIn("7-Day GDD (Base 10°C)", metric_labels)


if __name__ == "__main__":
    unittest.main()
