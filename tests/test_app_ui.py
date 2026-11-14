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
        at = AppTest.from_file(APP_PATH, default_timeout=20)
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


if __name__ == "__main__":
    unittest.main()
