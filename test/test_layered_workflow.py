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
    topic_overview: str = "",
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
        "topic_overview": topic_overview,
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
        self.assertIn("strategic impact", normalized["focal_points"][1]["topic_overview"])

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

    def test_optional_with_short_overview_downgrades_to_brief_only(self):
        plan = {
            "daily_overview": "Quiet day.",
            "today_pattern": "Small updates dominated.",
            "daily_brief_items": [],
            "focal_points": [
                _point("Minor Update", 1, OPTIONAL_DEEP, topic_overview="Worth watching."),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], BRIEF_ONLY)
        self.assertEqual(normalized["focal_points"][0]["topic_overview"], "")

    def test_optional_with_missing_overview_downgrades_to_brief_only(self):
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
        self.assertEqual(normalized["focal_points"][0]["topic_overview"], "")

    def test_optional_with_substantive_overview_survives(self):
        plan = {
            "daily_overview": "Mixed signals.",
            "today_pattern": "Sources disagreed on enterprise impact.",
            "daily_brief_items": [],
            "focal_points": [
                _point(
                    "Enterprise Pricing",
                    1,
                    OPTIONAL_DEEP,
                    topic_overview="Sources conflict on pricing timing, which affects enterprise budget planning.",
                ),
            ],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], OPTIONAL_DEEP)

    def test_extra_auto_deep_with_short_reason_downgrades_to_brief_only(self):
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
        self.assertEqual(normalized["focal_points"][1]["topic_overview"], "")

    def test_get_auto_deep_points_filters_strictly(self):
        plan = {
            "focal_points": [
                _point("Auto", 1, AUTO_DEEP),
                _point("Optional", 2, OPTIONAL_DEEP, topic_overview="Unresolved question affects roadmap decisions and planning cycles."),
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
                    topic_overview="Unresolved question affects roadmap decisions and planning cycles.",
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
            topic_overview="Unresolved timing affects downstream roadmap decisions.",
        )
        vague_point = _point("Vague", 3, "INVALID", topic_overview="Worth watching.")
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
        self.assertEqual(normalized["focal_points"][0]["topic_overview"], "")

    def test_optional_with_non_string_overview_downgrades_to_brief_only(self):
        point = _point("Malformed Optional", 1, OPTIONAL_DEEP)
        point["topic_overview"] = []
        plan = {
            "daily_overview": "Quiet day.",
            "today_pattern": "Small updates dominated.",
            "daily_brief_items": [],
            "focal_points": [point],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(normalized["focal_points"][0]["generation_mode"], BRIEF_ONLY)
        self.assertEqual(normalized["focal_points"][0]["topic_overview"], "")

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
        self.assertEqual(normalized["focal_points"][1]["topic_overview"], "")

    def test_optional_section_uses_topic_overview(self):
        point = _point(
            "Chip Supply",
            1,
            OPTIONAL_DEEP,
            topic_overview="Global chip supply chains remain uncertain, with key foundries reporting mixed demand signals that could shift AI hardware pricing.",
        )

        section = build_optional_analysis_section([point])

        self.assertIn("## Chip Supply", section)
        self.assertIn("Chip Supply happened.", section)
        self.assertIn("Global chip supply chains remain uncertain", section)

    def test_assemble_report_keeps_brief_first(self):
        report = assemble_layered_report(
            primary_brief="# Today Brief\n\n## What Happened\n- A happened.\n\n## Today's Pattern\nA larger shift.",
            deep_sections=["## Deep Topic\nAnalysis."],
            optional_points=[],
        )

        self.assertTrue(report.startswith("# Today Brief"))
        self.assertIn("## Deep Topic", report)

    def test_normalize_merges_overlapping_article_sets(self):
        platform_point = _point(
            "AI Platform Shift",
            1,
            AUTO_DEEP,
            deep_analysis_reason="Strategic platform impact changes enterprise roadmap decisions.",
        )
        platform_point["article_ids"] = ["1", "2", "3"]
        platform_point["brief_summary"] = "AI platforms changed pricing and access."
        pricing_point = _point(
            "Platform Pricing",
            2,
            OPTIONAL_DEEP,
            topic_overview="Pricing timing uncertainty affects enterprise budget planning across major cloud providers.",
        )
        pricing_point["article_ids"] = ["2", "3", "4"]
        pricing_point["brief_summary"] = "AI platform pricing changed."
        plan = {
            "daily_overview": "Platform competition intensified.",
            "today_pattern": "AI platforms moved toward enterprise pricing pressure.",
            "daily_brief_items": [],
            "focal_points": [platform_point, pricing_point],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(len(normalized["focal_points"]), 1)
        self.assertEqual(normalized["focal_points"][0]["article_ids"], ["1", "2", "3", "4"])
        self.assertEqual(normalized["focal_points"][0]["generation_mode"], AUTO_DEEP)

    def test_normalize_merges_same_strategic_implication_without_article_overlap(self):
        infrastructure_point = _point(
            "GPU Demand",
            1,
            AUTO_DEEP,
            deep_analysis_reason="Strategic infrastructure cost impact changes enterprise budget planning.",
        )
        infrastructure_point["article_ids"] = ["1"]
        infrastructure_point["relevance_description"] = "Cloud GPU demand raises AI infrastructure costs."
        infrastructure_point["reasoning"] = "Same strategic implication: enterprise budget pressure."
        capital_point = _point(
            "Cloud Capex",
            2,
            OPTIONAL_DEEP,
            topic_overview="Downstream budget impact uncertainty affects enterprise AI roadmap decisions and capital allocation.",
        )
        capital_point["article_ids"] = ["2"]
        capital_point["relevance_description"] = "Cloud capital spending raises AI infrastructure costs."
        capital_point["reasoning"] = "Same strategic implication: enterprise budget pressure."
        plan = {
            "daily_overview": "Infrastructure costs dominated.",
            "today_pattern": "AI infrastructure costs are pressuring enterprise budgets.",
            "daily_brief_items": [],
            "focal_points": [infrastructure_point, capital_point],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual([p["topic"] for p in normalized["focal_points"]], ["GPU Demand"])
        self.assertEqual(normalized["focal_points"][0]["article_ids"], ["1", "2"])

    def test_normalize_applies_article_count_budget_ceiling(self):
        points = []
        for index in range(1, 6):
            point = _point(f"Topic {index}", index, OPTIONAL_DEEP, topic_overview="Unresolved impact affects roadmap decisions and capital allocation.")
            point["article_ids"] = [str(article_id) for article_id in range(index * 3 - 2, index * 3 + 1)]
            points.append(point)
        points[-1]["article_ids"] = ["13", "14", "15", "16", "17"]
        plan = {
            "daily_overview": "Seventeen articles across several areas.",
            "today_pattern": "The day had several independent but bounded patterns.",
            "daily_brief_items": [],
            "focal_points": points,
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(len(normalized["focal_points"]), 4)
        self.assertEqual([p["topic"] for p in normalized["focal_points"]], ["Topic 1", "Topic 2", "Topic 3", "Topic 4"])

    def test_normalize_reenforces_auto_deep_limit_after_merge(self):
        first = _point(
            "Model Pricing",
            1,
            AUTO_DEEP,
            deep_analysis_reason="Strategic pricing impact changes enterprise budget planning.",
        )
        first["article_ids"] = ["1", "2"]
        duplicate = _point(
            "AI Model Price",
            2,
            AUTO_DEEP,
            deep_analysis_reason="Strategic pricing impact changes enterprise budget planning.",
        )
        duplicate["article_ids"] = ["2", "3"]
        independent = _point(
            "Chip Supply",
            3,
            AUTO_DEEP,
            deep_analysis_reason="Strategic supply risk affects infrastructure roadmap decisions.",
        )
        independent["article_ids"] = ["4"]
        plan = {
            "daily_overview": "Pricing and chips both moved.",
            "today_pattern": "AI economics shifted through pricing and supply pressure.",
            "daily_brief_items": [],
            "focal_points": [first, duplicate, independent],
            "discarded_items": [],
        }

        normalized = normalize_plan_layers(plan)

        self.assertEqual(len(normalized["focal_points"]), 2)
        self.assertEqual(
            [p["generation_mode"] for p in normalized["focal_points"]],
            [AUTO_DEEP, OPTIONAL_DEEP],
        )


class PlannerLayerContractTest(unittest.TestCase):
    def test_planner_prompt_mentions_layered_generation_contract(self):
        self.assertIn("generation_mode", PLANNER_SYSTEM_PROMPT)
        self.assertIn("BRIEF_ONLY", PLANNER_SYSTEM_PROMPT)
        self.assertIn("OPTIONAL_DEEP", PLANNER_SYSTEM_PROMPT)
        self.assertIn("AUTO_DEEP", PLANNER_SYSTEM_PROMPT)
        self.assertIn("最多 1 个", PLANNER_SYSTEM_PROMPT)
        self.assertIn("不能偷偷生成", PLANNER_SYSTEM_PROMPT)
        self.assertIn("daily_brief_items", PLANNER_SYSTEM_PROMPT)
        self.assertIn("today_pattern", PLANNER_SYSTEM_PROMPT)
        self.assertIn("auto_deep_exception", PLANNER_SYSTEM_PROMPT)
        self.assertIn("topic_overview", PLANNER_SYSTEM_PROMPT)
        self.assertIn("BRIEF_ONLY does not need to become a focal point", PLANNER_SYSTEM_PROMPT)
        self.assertIn("11-20 articles", PLANNER_SYSTEM_PROMPT)
        self.assertIn("target 2-3, ceiling 4", PLANNER_SYSTEM_PROMPT)
        self.assertIn("same strategic implication", PLANNER_SYSTEM_PROMPT)

    def test_planner_prompt_uses_today_pattern_as_only_day_synthesis_field(self):
        self.assertIn("today_pattern", PLANNER_SYSTEM_PROMPT)
        self.assertNotIn("daily_overview", PLANNER_SYSTEM_PROMPT)

    def test_daily_overview_is_only_legacy_optional_plan_field(self):
        from agent.models import AgentPlanResult

        self.assertIn("today_pattern", AgentPlanResult.__required_keys__)
        self.assertIn("daily_overview", AgentPlanResult.__optional_keys__)


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
                  "daily_brief_items": [
                    {
                      "title": "Policy changed",
                      "summary": "Policy shifted.",
                      "importance": "It affects deployment.",
                      "article_ids": [1, 2]
                    }
                  ],
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
            self.assertEqual(result["daily_brief_items"][0]["article_ids"], ["1", "2"])
            self.assertEqual(state["plan"], result)

        import asyncio

        asyncio.run(_run_test())


class PrimaryBriefWriterTest(unittest.TestCase):
    def test_primary_brief_prompt_enforces_one_minute_structure(self):
        from agent.tools.writing_tool import _build_primary_brief_prompt

        plan = {
            "today_pattern": "Infrastructure spending is becoming the main AI signal.",
            "daily_brief_items": [
                {
                    "title": "GPU Orders",
                    "summary": "Cloud providers increased GPU orders.",
                    "importance": "This points to sustained AI infrastructure demand.",
                    "article_ids": ["1"],
                }
            ],
            "focal_points": [
                _point("GPU Orders", 1, "AUTO_DEEP", deep_analysis_reason="Large capital allocation.")
            ],
        }

        prompt = _build_primary_brief_prompt(plan)
        text = "\n".join(message.content for message in prompt)

        self.assertIn("What Happened", text)
        self.assertIn("Today's Pattern", text)
        self.assertIn("5-8", text)
        self.assertIn("complete on its own", text)

    def test_write_primary_brief_calls_client(self):
        from agent.tools.writing_tool import write_primary_brief

        async def _run_test():
            client = MagicMock()
            client.completion = AsyncMock(return_value="# Today Brief\n\n## What Happened\n- A\n\n## Today's Pattern\nB")
            result = await write_primary_brief(client, {"focal_points": [], "daily_brief_items": [], "today_pattern": "B"})
            self.assertTrue(result.startswith("# Today Brief"))
            client.completion.assert_awaited_once()

        import asyncio

        asyncio.run(_run_test())


class ReadingBurdenRegressionTest(unittest.TestCase):
    def test_final_report_does_not_put_optional_before_deep_or_brief(self):
        report = assemble_layered_report(
            primary_brief="# Today Brief\n\n## What Happened\n- One\n\n## Today's Pattern\nA synthesis.",
            deep_sections=["## Market Structure\nDeep analysis."],
            optional_points=[
                _point(
                    "Secondary Topic",
                    2,
                    OPTIONAL_DEEP,
                    topic_overview="Customer adoption patterns are shifting, with early adopters showing hesitation on new pricing models.",
                )
            ],
        )

        brief_index = report.index("# Today Brief")
        deep_index = report.index("## Market Structure")
        optional_index = report.index("## Secondary Topic")

        self.assertLess(brief_index, deep_index)
        self.assertLess(deep_index, optional_index)


if __name__ == "__main__":
    unittest.main()
