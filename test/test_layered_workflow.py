import unittest

from agent.workflow.layered import (
    AUTO_DEEP,
    BRIEF_ONLY,
    OPTIONAL_DEEP,
    build_optional_analysis_section,
    get_auto_deep_points,
    normalize_plan_layers,
    assemble_layered_report,
)


def _point(
    topic: str,
    priority: int,
    generation_mode: str,
    why_expand: str = "",
    deep_analysis_reason: str = "",
    auto_deep_exception: str = "",
):
    return {
        "priority": priority,
        "topic": topic,
        "match_type": "GLOBAL_STRATEGIC",
        "relevance_description": "This story affects the market.",
        "strategy": "SUMMARIZE",
        "article_ids": [str(priority)],
        "reasoning": "High-value story.",
        "search_query": "",
        "writing_guide": "Explain the impact.",
        "history_memory_id": [],
        "generation_mode": generation_mode,
        "brief_summary": f"{topic} happened.",
        "why_expand": why_expand,
        "deep_analysis_reason": deep_analysis_reason,
        "auto_deep_exception": auto_deep_exception,
    }


class LayeredWorkflowTest(unittest.TestCase):
    def test_normalize_keeps_one_auto_deep_by_default(self):
        plan = {
            "daily_overview": "Market day.",
            "today_pattern": "Markets favored infrastructure over demos.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Topic A", 1, AUTO_DEEP, deep_analysis_reason="Major strategic impact."),
                _point("Topic B", 2, AUTO_DEEP, deep_analysis_reason="Major strategic impact."),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(
            [p["generation_mode"] for p in normalized["focal_points"]],
            [AUTO_DEEP, OPTIONAL_DEEP],
        )
        self.assertIn("strategic impact", normalized["focal_points"][1]["why_expand"])

    def test_normalize_allows_second_auto_deep_with_exception(self):
        plan = {
            "daily_overview": "Two unrelated shocks.",
            "today_pattern": "Policy and model releases moved separately.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Policy Shock", 1, AUTO_DEEP, deep_analysis_reason="Regulatory impact."),
                _point(
                    "Model Shock",
                    2,
                    AUTO_DEEP,
                    deep_analysis_reason="Platform impact.",
                    auto_deep_exception="Independent high-impact story that cannot be merged with policy shock.",
                ),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(
            [p["generation_mode"] for p in normalized["focal_points"]],
            [AUTO_DEEP, AUTO_DEEP],
        )

    def test_optional_with_vague_reason_downgrades_to_brief_only(self):
        plan = {
            "daily_overview": "Quiet day.",
            "today_pattern": "Small updates dominated.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Minor Update", 1, OPTIONAL_DEEP, why_expand="Worth watching."),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], BRIEF_ONLY)
        self.assertEqual(normalized["focal_points"][0]["why_expand"], "")

    def test_optional_with_concrete_reason_survives(self):
        plan = {
            "daily_overview": "Mixed signals.",
            "today_pattern": "Sources disagreed on enterprise impact.",
            "daily_brief_items": [],
            "focal_points": [
                _point(
                    "Enterprise Pricing",
                    1,
                    OPTIONAL_DEEP,
                    why_expand="Sources conflict on pricing timing, which affects enterprise budget planning.",
                ),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], OPTIONAL_DEEP)

    def test_get_auto_deep_points_filters_strictly(self):
        plan = {
            "focal_points": [
                _point("Auto", 1, AUTO_DEEP),
                _point("Optional", 2, OPTIONAL_DEEP, why_expand="Unresolved question affects roadmap decisions."),
                _point("Brief", 3, BRIEF_ONLY),
            ]
        }

        self.assertEqual([p["topic"] for p in get_auto_deep_points(plan)], ["Auto"])

    def test_optional_section_uses_specific_reason(self):
        point = _point(
            "Chip Supply",
            1,
            OPTIONAL_DEEP,
            why_expand="Unresolved supply timing could change AI infrastructure costs.",
        )

        section = build_optional_analysis_section([point])

        self.assertIn("## Optional Analysis", section)
        self.assertIn("Chip Supply happened.", section)
        self.assertIn("Unresolved supply timing", section)

    def test_assemble_report_keeps_brief_first(self):
        report = assemble_layered_report(
            primary_brief="# Today Brief\n\n## What Happened\n- A happened.\n\n## Today's Pattern\nA larger shift.",
            deep_sections=["## Deep Topic\nAnalysis."],
            optional_points=[],
        )

        self.assertTrue(report.startswith("# Today Brief"))
        self.assertIn("## Deep Analysis\n\n## Deep Topic", report)


if __name__ == "__main__":
    unittest.main()
