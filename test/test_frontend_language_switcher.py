from pathlib import Path
import unittest


ROOT = Path("/home/faust/dev/FlashAiNews")


class FrontendLanguageSwitcherTest(unittest.TestCase):
    def test_layout_contains_compact_cross_language_switcher_copy(self):
        layout_tsx = (ROOT / "apps/frontend/src/components/Layout.tsx").read_text()

        self.assertIn("language-switcher", layout_tsx)
        self.assertIn('const alternateLanguage = i18n.resolvedLanguage === "en" ? "zh" : "en";', layout_tsx)
        self.assertIn('{i18n.resolvedLanguage === "en" ? "中" : "EN"}', layout_tsx)
        self.assertIn('aria-label="Language switcher"', layout_tsx)


if __name__ == "__main__":
    unittest.main()
