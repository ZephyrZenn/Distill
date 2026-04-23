import unittest
from unittest.mock import MagicMock, patch

from apps.backend.services import brief_service


class OptionalExpansionPersistenceTest(unittest.TestCase):
    def test_insert_brief_persists_expandable_topics(self):
        cursor = MagicMock()
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor

        expandable_topics = [
            {
                "topic_id": "1-ai-pricing",
                "topic": "AI Pricing",
                "topic_overview": "Enterprise budget planning faces uncertainty from unresolved AI pricing changes.",
                "strategy": "SUMMARIZE",
                "search_query": "",
                "history_memory_id": [],
                "focal_point": {"topic": "AI Pricing", "article_ids": ["1"]},
                "articles": [{"id": "1", "title": "A", "url": "u", "summary": "s", "pub_date": "", "score": 9, "reasoning": "r"}],
            }
        ]

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            brief_service._insert_brief([7], "# Today Brief", [], "Overview", expandable_topics)

        sql = cursor.execute.call_args.args[0]
        params = cursor.execute.call_args.args[1]
        self.assertIn("expandable_topics", sql)
        self.assertIn('"topic_id": "1-ai-pricing"', params[6])

    def test_get_brief_by_id_returns_expandable_topics(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            12,
            "# Today Brief",
            "2026-04-16",
            [7],
            "Summary",
            "Overview",
            "en",
            [],
            [{"topic_id": "1-ai-pricing", "topic": "AI Pricing"}],
        )
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            brief = brief_service.get_brief_by_id(12)

        self.assertEqual(brief.expandable_topics[0]["topic_id"], "1-ai-pricing")
        self.assertEqual(brief.target_language, "en")


if __name__ == "__main__":
    unittest.main()
