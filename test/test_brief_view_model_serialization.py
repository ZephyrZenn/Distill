import unittest
from datetime import datetime

from apps.backend.models.view_model import FeedBriefResponse
from core.models.feed import FeedBrief


class BriefViewModelSerializationTest(unittest.TestCase):
    def test_expandable_topics_are_camel_cased_in_api_response(self):
        brief = FeedBrief(
            id=12,
            content="# Today Brief",
            pub_date=datetime(2026, 4, 16),
            expandable_topics=[
                {
                    "topic_id": "1-ai-pricing",
                    "topic": "AI Pricing",
                    "why_expand": "Unresolved budget impact affects roadmap decisions.",
                    "strategy": "SUMMARIZE",
                    "search_query": "AI pricing enterprise budget",
                    "history_memory_id": [3],
                    "articles": [
                        {
                            "id": "1",
                            "title": "AI Pricing",
                            "url": "https://example.com/1",
                            "summary": "Pricing changed.",
                            "pub_date": "2026-04-16",
                            "score": 9,
                            "reasoning": "Important.",
                        }
                    ],
                }
            ],
        )

        response = FeedBriefResponse(
            success=True,
            data=brief.to_view_model({}, include_content=True),
        ).model_dump(by_alias=True)

        topic = response["data"]["expandableTopics"][0]
        article = topic["articles"][0]
        self.assertEqual(topic["topicId"], "1-ai-pricing")
        self.assertEqual(
            topic["whyExpand"],
            "Unresolved budget impact affects roadmap decisions.",
        )
        self.assertEqual(topic["searchQuery"], "AI pricing enterprise budget")
        self.assertEqual(topic["historyMemoryId"], [3])
        self.assertEqual(article["pubDate"], "2026-04-16")
        self.assertNotIn("topic_id", topic)
        self.assertNotIn("pub_date", article)


if __name__ == "__main__":
    unittest.main()
