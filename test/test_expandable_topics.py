import unittest

from agent.workflow.expansion import build_expandable_topics


def _point(topic: str, priority: int, generation_mode: str):
    return {
        "priority": priority,
        "topic": topic,
        "match_type": "GLOBAL_STRATEGIC",
        "relevance_description": "This affects AI infrastructure decisions.",
        "strategy": "SUMMARIZE",
        "generation_mode": generation_mode,
        "brief_summary": f"{topic} happened.",
        "topic_overview": "Downstream budget impact remains uncertain across enterprise planning cycles.",
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
        topics = build_expandable_topics(plan)

        self.assertEqual(len(topics), 1)
        topic = topics[0]
        self.assertEqual(topic["focal_point"]["topic"], "Optional Topic")
        self.assertEqual(topic["topic_id"], "2-optional-topic")
        self.assertEqual(topic["focal_point"]["topic_overview"], "Downstream budget impact remains uncertain across enterprise planning cycles.")
        self.assertEqual(topic["focal_point"]["generation_mode"], "OPTIONAL_DEEP")
        self.assertNotIn("articles", topic)

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

        topics = build_expandable_topics(plan)

        self.assertEqual(topics[0]["topic_id"], "7-gpu-supply-cloud-cost")

    def test_build_normalizes_before_collecting_optional_topics(self):
        plan = {
            "daily_overview": "Day.",
            "focal_points": [
                _point("Vague Topic", 1, "OPTIONAL_DEEP"),
            ],
            "discarded_items": [],
        }
        plan["focal_points"][0]["topic_overview"] = "Worth watching."

        topics = build_expandable_topics(plan)

        self.assertEqual(topics, [])

    def test_focal_point_snapshot_does_not_alias_original_plan(self):
        plan = {
            "daily_overview": "Day.",
            "focal_points": [
                _point("Optional Topic", 2, "OPTIONAL_DEEP"),
            ],
            "discarded_items": [],
        }

        topics = build_expandable_topics(plan)
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
                    "topic_overview": "Platform pricing shifts create downstream uncertainty for enterprise budget allocation.",
                },
            ],
            "discarded_items": [],
        }

        topics = build_expandable_topics(plan)

        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["topic_id"], "5-platform-shift")


if __name__ == "__main__":
    unittest.main()
