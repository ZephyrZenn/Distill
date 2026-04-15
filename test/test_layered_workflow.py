import unittest

from agent.workflow.layered import (
    AUTO_DEEP,
    BRIEF_ONLY,
    OPTIONAL_DEEP,
    build_optional_analysis_section,
    get_auto_deep_points,
    get_optional_deep_points,
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

    def test_optional_with_missing_reason_downgrades_to_brief_only(self):
        plan = {
            "daily_overview": "Quiet day.",
            "today_pattern": "Small updates dominated.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Minor Update", 1, OPTIONAL_DEEP),
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

    def test_extra_auto_deep_with_vague_reason_downgrades_to_brief_only(self):
        second_point = _point(
            "Topic B",
            2,
            AUTO_DEEP,
            deep_analysis_reason="Worth watching.",
        )
        second_point["reasoning"] = "Important topic."
        plan = {
            "daily_overview": "Market day.",
            "today_pattern": "Markets favored infrastructure over demos.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Topic A", 1, AUTO_DEEP, deep_analysis_reason="Major strategic impact."),
                second_point,
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(
            [p["generation_mode"] for p in normalized["focal_points"]],
            [AUTO_DEEP, BRIEF_ONLY],
        )
        self.assertEqual(normalized["focal_points"][1]["why_expand"], "")

    def test_get_auto_deep_points_filters_strictly(self):
        plan = {
            "focal_points": [
                _point("Auto", 1, AUTO_DEEP),
                _point("Optional", 2, OPTIONAL_DEEP, why_expand="Unresolved question affects roadmap decisions."),
                _point("Brief", 3, BRIEF_ONLY),
            ]
        }

        self.assertEqual([p["topic"] for p in get_auto_deep_points(plan)], ["Auto"])

    def test_get_optional_deep_points_filters_strictly(self):
        plan = {
            "focal_points": [
                _point("Auto", 1, AUTO_DEEP),
                _point(
                    "Optional",
                    2,
                    OPTIONAL_DEEP,
                    why_expand="Unresolved question affects roadmap decisions.",
                ),
                _point("Brief", 3, BRIEF_ONLY),
            ]
        }

        self.assertEqual([p["topic"] for p in get_optional_deep_points(plan)], ["Optional"])

    def test_missing_today_pattern_copies_daily_overview(self):
        plan = {
            "daily_overview": "Market day.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Topic A", 1, BRIEF_ONLY),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["today_pattern"], "Market day.")

    def test_normalize_deep_copies_input_without_mutating_original_plan(self):
        plan = {
            "daily_overview": "Market day.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Topic B", 2, BRIEF_ONLY),
                _point("Topic A", 1, BRIEF_ONLY),
            ],
            "discarded_items": [],
        }
        original = {
            "daily_overview": "Market day.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Topic B", 2, BRIEF_ONLY),
                _point("Topic A", 1, BRIEF_ONLY),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertIsNot(normalized, plan)
        self.assertEqual([p["topic"] for p in normalized["focal_points"]], ["Topic A", "Topic B"])
        self.assertEqual(plan, original)

    def test_invalid_planner_data_raises_clear_value_errors(self):
        cases = [
            (
                {"daily_overview": "Bad plan.", "focal_points": "not a list", "discarded_items": []},
                "focal_points must be a list",
            ),
            (
                {"daily_overview": "Bad plan.", "focal_points": ["bad point"], "discarded_items": []},
                "focal_points[0] must be an object",
            ),
            (
                {
                    "daily_overview": "Bad plan.",
                    "focal_points": [
                        {
                            "priority": 1,
                            "strategy": "SUMMARIZE",
                        }
                    ],
                    "discarded_items": [],
                },
                "focal_points[0] missing required field: topic",
            ),
            (
                {
                    "daily_overview": "Bad plan.",
                    "focal_points": [
                        {
                            "priority": 1,
                            "topic": "Missing strategy",
                        }
                    ],
                    "discarded_items": [],
                },
                "focal_points[0] missing required field: strategy",
            ),
            (
                {
                    "daily_overview": "Bad plan.",
                    "focal_points": [
                        {
                            "topic": "Missing priority",
                            "strategy": "SUMMARIZE",
                        }
                    ],
                    "discarded_items": [],
                },
                "focal_points[0] missing required field: priority",
            ),
            (
                {
                    "daily_overview": "Bad plan.",
                    "focal_points": [
                        {
                            "priority": "high",
                            "topic": "Bad priority",
                            "strategy": "SUMMARIZE",
                        }
                    ],
                    "discarded_items": [],
                },
                "focal_points[0] priority must be an integer",
            ),
        ]

        for plan, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as error:
                    normalize_plan_layers(plan)
                self.assertEqual(str(error.exception), message)

    def test_priority_rejects_non_integer_values(self):
        for priority in ("1", 1.0, True):
            with self.subTest(priority=priority):
                plan = {
                    "daily_overview": "Bad plan.",
                    "focal_points": [
                        {
                            "priority": priority,
                            "topic": "Bad priority",
                            "strategy": "SUMMARIZE",
                        }
                    ],
                    "discarded_items": [],
                }

                with self.assertRaises(ValueError) as error:
                    normalize_plan_layers(plan)
                self.assertEqual(
                    str(error.exception),
                    "focal_points[0] priority must be an integer",
                )

    def test_invalid_generation_mode_normalizes_by_strategy_and_reason_quality(self):
        flash_point = _point("Flash", 1, "INVALID")
        flash_point["strategy"] = "FLASH_NEWS"
        concrete_point = _point(
            "Concrete",
            2,
            "INVALID",
            why_expand="Unresolved timing affects downstream roadmap decisions.",
        )
        vague_point = _point("Vague", 3, "INVALID", why_expand="Worth watching.")
        plan = {
            "daily_overview": "Market day.",
            "today_pattern": "Markets favored infrastructure over demos.",
            "daily_brief_items": [],
            "focal_points": [
                vague_point,
                concrete_point,
                flash_point,
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(
            [p["generation_mode"] for p in normalized["focal_points"]],
            [BRIEF_ONLY, OPTIONAL_DEEP, BRIEF_ONLY],
        )

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
