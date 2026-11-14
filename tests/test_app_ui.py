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


if __name__ == "__main__":
    unittest.main()
