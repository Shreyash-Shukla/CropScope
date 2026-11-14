import unittest

from i18n import (
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    get_code_from_label,
    get_language_names,
    get_quick_prompts,
    t,
)


class I18nTests(unittest.TestCase):
    def test_supported_languages_presence(self):
        expected = ["en", "hi", "pa", "mr", "te", "ta", "gu", "bn", "kn", "ml"]
        for code in expected:
            self.assertIn(code, SUPPORTED_LANGUAGES)
            self.assertIn("label", SUPPORTED_LANGUAGES[code])
            self.assertIn("native", SUPPORTED_LANGUAGES[code])

    def test_translations_and_fallback(self):
        # Valid key in English and Hindi
        en_title = t("kisan_mitra_title", "en")
        hi_title = t("kisan_mitra_title", "hi")
        self.assertIn("Kisan Mitra", en_title)
        self.assertIn("किसान मित्र", hi_title)

        # Non-existent language falls back to English
        fallback = t("kisan_mitra_title", "nonexistent")
        self.assertEqual(fallback, en_title)

        # Non-existent key returns key itself
        self.assertEqual(t("unknown_key_xyz", "hi"), "unknown_key_xyz")

    def test_quick_prompts(self):
        en_prompts = get_quick_prompts("en")
        hi_prompts = get_quick_prompts("hi")
        pa_prompts = get_quick_prompts("pa")

        self.assertGreaterEqual(len(en_prompts), 3)
        self.assertGreaterEqual(len(hi_prompts), 3)
        self.assertGreaterEqual(len(pa_prompts), 3)

        # Fallback to English for unknown language
        unknown_prompts = get_quick_prompts("es")
        self.assertEqual(unknown_prompts, en_prompts)

    def test_get_code_from_label(self):
        self.assertEqual(get_code_from_label("English"), "en")
        self.assertEqual(get_code_from_label("हिन्दी (Hindi)"), "hi")
        self.assertEqual(get_code_from_label("ਪੰਜਾਬੀ (Punjabi)"), "pa")
        self.assertEqual(get_code_from_label("मराठी (Marathi)"), "mr")
        self.assertEqual(get_code_from_label("Unknown"), "en")

    def test_get_language_names(self):
        names = get_language_names()
        self.assertEqual(len(names), len(SUPPORTED_LANGUAGES))
        self.assertIn("English", names)
        self.assertIn("हिन्दी (Hindi)", names)


if __name__ == "__main__":
    unittest.main()
