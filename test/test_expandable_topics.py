import unittest

from agent.workflow.expansion import build_expandable_topics


def _article(article_id: str):
    return {
        "id": article_id,
        "title": f"Article {article_id}",
        "url": f"https://example.com/{article_id}",
        "summary": f"Summary {article_id}",
        "pub_date": "2026-04-16",
        "score": 9,
        "reasoning": f"Reason {article_id}",
        "content": f"Full content {article_id}",
    }


def _point(topic: str, priority: int, generation_mode: str):
    return {
        "priority": priority,
        "topic": topic,
        "match_type": "GLOBAL_STRATEGIC",
        "relevance_description": "This affects AI infrastructure decisions.",
        "strategy": "SUMMARIZE",
        "generation_mode": generation_mode,
        "brief_summary": f"{topic} happened.",
        "why_expand": "Unresolved downstream impact affects budget planning.",
        "article_ids": [str(priority)],
        "reasoning": "Strategic implication remains unresolved.",
        "search_query": "",
        "writing_guide": "Explain the strategic impact.",
        "history_memory_id": [101],
    }


class ExpandableTopicsTest(unittest.TestCase):
    def test_builds_only_optional_deep_topics(self):
        brief_point = _point("Brief Topic", 3, "BRIEF_ONLY")
        brief_point["reasoning"] = "A separate non-strategic update."
        brief_point["writing_guide"] = "Keep this to a short recap."
        brief_point["brief_summary"] = "Brief Topic happened."

        plan = {
            "daily_overview": "AI infrastructure moved.",
            "today_pattern": "Infrastructure cost pressure dominated.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Optional Topic", 2, "OPTIONAL_DEEP"),
                brief_point,
            ],
            "discarded_items": [],
        }
        articles = [_article("2"), _article("3")]

        topics = build_expandable_topics(plan, articles)

        self.assertEqual(len(topics), 1)
        topic = topics[0]
        self.assertEqual(topic["focal_point"]["topic"], "Optional Topic")
        self.assertEqual(topic["topic_id"], "2-optional-topic")
        self.assertEqual(topic["focal_point"]["why_expand"], "Unresolved downstream impact affects budget planning.")
        self.assertEqual(topic["focal_point"]["generation_mode"], "OPTIONAL_DEEP")
        self.assertEqual(topic["articles"][0]["id"], "2")
        self.assertNotIn("content", topic["articles"][0])

    def test_topic_id_is_stable_and_url_safe(self):
        plan = {
            "daily_overview": "Day.",
            "focal_points": [
                {
                    **_point("GPU Supply / Cloud Cost", 7, "OPTIONAL_DEEP"),
                    "article_ids": ["a", "b"],
                }
            ],
            "discarded_items": [],
        }

        topics = build_expandable_topics(plan, [_article("a"), _article("b")])

        self.assertEqual(topics[0]["topic_id"], "7-gpu-supply-cloud-cost")

    def test_build_normalizes_before_collecting_optional_topics(self):
        plan = {
            "daily_overview": "Day.",
            "focal_points": [
                _point("Vague Topic", 1, "OPTIONAL_DEEP"),
            ],
            "discarded_items": [],
        }
        plan["focal_points"][0]["why_expand"] = "Worth watching."

        topics = build_expandable_topics(plan, [_article("1")])

        self.assertEqual(topics, [])

    def test_focal_point_snapshot_does_not_alias_original_plan(self):
        plan = {
            "daily_overview": "Day.",
            "focal_points": [
                _point("Optional Topic", 2, "OPTIONAL_DEEP"),
            ],
            "discarded_items": [],
        }

        topics = build_expandable_topics(plan, [_article("2")])
        topics[0]["focal_point"]["article_ids"].append("999")

        self.assertEqual(plan["focal_points"][0]["article_ids"], ["2"])

    def test_topic_id_uses_source_priority_after_overlap_merge(self):
        plan = {
            "daily_overview": "Day.",
            "focal_points": [
                {
                    **_point("Platform Shift", 5, "OPTIONAL_DEEP"),
                    "article_ids": ["1", "2"],
                },
                {
                    **_point("Platform Pricing", 6, "OPTIONAL_DEEP"),
                    "article_ids": ["1", "2", "3"],
                    "reasoning": "Pricing and platform changes overlap.",
                    "why_expand": "Unresolved pricing and platform impact affects budget planning.",
                },
            ],
            "discarded_items": [],
        }

        topics = build_expandable_topics(plan, [_article("1"), _article("2"), _article("3")])

        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["topic_id"], "5-platform-shift")


if __name__ == "__main__":
    unittest.main()
