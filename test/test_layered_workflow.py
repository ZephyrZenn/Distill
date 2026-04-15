import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.prompts import PLANNER_SYSTEM_PROMPT
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

    def test_non_string_generation_mode_with_flash_news_becomes_brief_only(self):
        point = _point("Flash", 1, "INVALID")
        point["generation_mode"] = []
        point["strategy"] = "FLASH_NEWS"
        plan = {
            "daily_overview": "Market day.",
            "today_pattern": "Markets favored infrastructure over demos.",
            "daily_brief_items": [],
            "focal_points": [point],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], BRIEF_ONLY)

    def test_non_string_generation_mode_without_concrete_reason_becomes_brief_only(self):
        point = _point("Summary", 1, "INVALID")
        point["generation_mode"] = []
        plan = {
            "daily_overview": "Market day.",
            "today_pattern": "Markets favored infrastructure over demos.",
            "daily_brief_items": [],
            "focal_points": [point],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], BRIEF_ONLY)
        self.assertEqual(normalized["focal_points"][0]["why_expand"], "")

    def test_optional_with_non_string_reason_downgrades_to_brief_only(self):
        point = _point("Malformed Optional", 1, OPTIONAL_DEEP)
        point["why_expand"] = []
        plan = {
            "daily_overview": "Quiet day.",
            "today_pattern": "Small updates dominated.",
            "daily_brief_items": [],
            "focal_points": [point],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], BRIEF_ONLY)
        self.assertEqual(normalized["focal_points"][0]["why_expand"], "")

    def test_non_string_auto_deep_exception_does_not_allow_second_auto(self):
        second_point = _point(
            "Topic B",
            2,
            AUTO_DEEP,
            deep_analysis_reason="Major strategic impact.",
        )
        second_point["auto_deep_exception"] = []
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
            [AUTO_DEEP, OPTIONAL_DEEP],
        )

    def test_extra_auto_with_non_string_reasons_downgrades_to_brief_only(self):
        second_point = _point("Topic B", 2, AUTO_DEEP)
        second_point["deep_analysis_reason"] = []
        second_point["reasoning"] = []
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


class PlannerLayerContractTest(unittest.TestCase):
    def test_planner_prompt_mentions_layered_generation_contract(self):
        self.assertIn("generation_mode", PLANNER_SYSTEM_PROMPT)
        self.assertIn("BRIEF_ONLY", PLANNER_SYSTEM_PROMPT)
        self.assertIn("OPTIONAL_DEEP", PLANNER_SYSTEM_PROMPT)
        self.assertIn("AUTO_DEEP", PLANNER_SYSTEM_PROMPT)
        self.assertIn("最多 1 个", PLANNER_SYSTEM_PROMPT)
        self.assertIn("不能偷偷生成", PLANNER_SYSTEM_PROMPT)


class AgentPlannerNormalizationTest(unittest.TestCase):
    def test_plan_normalizes_generation_modes_before_storing_state(self):
        from agent.workflow.planner import AgentPlanner

        async def _run_test():
            client = MagicMock()
            client.completion = AsyncMock(
                return_value="""
                {
                  "daily_overview": "Two big stories.",
                  "today_pattern": "The day split between policy and platforms.",
                  "daily_brief_items": [],
                  "focal_points": [
                    {
                      "priority": 1,
                      "topic": "Policy",
                      "match_type": "GLOBAL_STRATEGIC",
                      "relevance_description": "Regulation affects AI deployment.",
                      "strategy": "SUMMARIZE",
                      "article_ids": ["1"],
                      "reasoning": "Major regulation.",
                      "search_query": "",
                      "writing_guide": "Explain impact.",
                      "history_memory_id": [],
                      "generation_mode": "AUTO_DEEP",
                      "brief_summary": "Policy changed.",
                      "deep_analysis_reason": "Regulation changes deployment strategy."
                    },
                    {
                      "priority": 2,
                      "topic": "Platform",
                      "match_type": "GLOBAL_STRATEGIC",
                      "relevance_description": "Platform affects developers.",
                      "strategy": "SUMMARIZE",
                      "article_ids": ["2"],
                      "reasoning": "Major platform shift.",
                      "search_query": "",
                      "writing_guide": "Explain platform impact.",
                      "history_memory_id": [],
                      "generation_mode": "AUTO_DEEP",
                      "brief_summary": "Platform changed.",
                      "deep_analysis_reason": "Platform changes developer roadmap."
                    }
                  ],
                  "discarded_items": []
                }
                """
            )
            planner = AgentPlanner(client)
            state = {
                "raw_articles": [{"id": "1", "title": "A", "url": "u", "summary": "s", "pub_date": ""}],
                "focus": "AI",
                "log_history": [],
                "history_memories": {},
                "scored_articles": [],
                "groups": [],
                "status": "PENDING",
                "created_at": None,
            }

            with patch.object(planner, "_rank_articles", AsyncMock(return_value=[
                {"id": "1", "title": "A", "url": "u", "summary": "s", "pub_date": "", "score": 9, "reasoning": "r"}
            ])), patch("agent.workflow.planner.find_keywords_with_llm", AsyncMock(return_value=[])), patch(
                "agent.workflow.planner.search_memory", AsyncMock(return_value={})
            ):
                result = await planner.plan(state)

            self.assertEqual(result["focal_points"][0]["generation_mode"], "AUTO_DEEP")
            self.assertEqual(result["focal_points"][1]["generation_mode"], "OPTIONAL_DEEP")
            self.assertEqual(state["plan"], result)

        import asyncio

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
