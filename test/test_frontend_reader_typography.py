from pathlib import Path
import unittest


ROOT = Path("/home/faust/dev/FlashAiNews")


class FrontendReaderTypographyTest(unittest.TestCase):
    def test_summary_page_uses_dedicated_reader_typography_class(self):
        content = (ROOT / "apps/frontend/src/pages/SummaryPage.tsx").read_text()
        self.assertIn("summary-reader-body", content)

    def test_reader_typography_tokens_exist(self):
        index_css = (ROOT / "apps/frontend/src/styles/index.css").read_text()
        app_css = (ROOT / "apps/frontend/src/styles/app.css").read_text()

        self.assertIn("--font-reading:", index_css)
        self.assertIn(".summary-reader-body", app_css)
        self.assertIn('--font-reading: "IBM Plex Sans", "Noto Sans SC"', index_css)
        self.assertIn(".summary-reader .prose {", app_css)
        self.assertIn("font-family: var(--font-reading) !important;", app_css)
        self.assertIn("font-weight: 400 !important;", app_css)


if __name__ == "__main__":
    unittest.main()
