import unittest
from datetime import datetime

from apps.backend.models.view_model import FeedBriefResponse
from core.models.feed import FeedBrief


class BriefViewModelSerializationTest(unittest.TestCase):
    def test_expandable_topics_project_to_topic_id_and_topic_only(self):
        brief = FeedBrief(
            id=12,
            content="# Today Brief",
            pub_date=datetime(2026, 4, 16),
            expandable_topics=[
                {
                    "topic_id": "1-ai-pricing",
                    "focal_point": {
                        "topic": "AI Pricing",
                        "topic_overview": "Enterprise budget planning faces uncertainty from unresolved AI pricing changes.",
                    },
                }
            ],
        )

        response = FeedBriefResponse(
            success=True,
            data=brief.to_view_model({}, include_content=True),
        ).model_dump(by_alias=True)

        topic = response["data"]["expandableTopics"][0]
        self.assertEqual(topic["topicId"], "1-ai-pricing")
        self.assertEqual(topic["topic"], "AI Pricing")
        self.assertNotIn("topic_id", topic)
        self.assertNotIn("topicOverview", topic)

    def test_expandable_topics_is_null_when_content_not_included(self):
        brief = FeedBrief(
            id=12,
            content="# Today Brief",
            pub_date=datetime(2026, 4, 16),
            expandable_topics=[
                {
                    "topic_id": "1-ai-pricing",
                    "focal_point": {"topic": "AI Pricing"},
                }
            ],
        )

        response = FeedBriefResponse(
            success=True,
            data=brief.to_view_model({}, include_content=False),
        ).model_dump(by_alias=True)

        self.assertIsNone(response["data"]["expandableTopics"])


if __name__ == "__main__":
    unittest.main()
