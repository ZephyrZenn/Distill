import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.workflow.executor import AgentExecutor


def _article(article_id: str):
    return {
        "id": article_id,
        "title": f"Article {article_id}",
        "url": f"https://example.com/{article_id}",
        "summary": "Summary",
        "pub_date": "",
        "score": 9,
        "reasoning": "Important",
    }


def _point(topic: str, priority: int, generation_mode: str, strategy: str = "SUMMARIZE"):
    return {
        "priority": priority,
        "topic": topic,
        "match_type": "GLOBAL_STRATEGIC",
        "relevance_description": "Important to the market.",
        "strategy": strategy,
        "article_ids": [str(priority)],
        "reasoning": "Important",
        "search_query": "",
        "writing_guide": "Explain impact.",
        "history_memory_id": [],
        "generation_mode": generation_mode,
        "brief_summary": f"{topic} happened.",
        "why_expand": "Unresolved downstream impact affects roadmap decisions.",
        "deep_analysis_reason": "Major strategic impact.",
    }


class WorkflowExecutorLayeringTest(unittest.TestCase):
    def test_execute_only_deep_writes_auto_deep_topics(self):
        async def _run_test():
            client = MagicMock()
            executor = AgentExecutor(client)
            state = {
                "plan": {
                    "daily_overview": "Overview",
                    "today_pattern": "Pattern",
                    "daily_brief_items": [],
                    "focal_points": [
                        _point("Auto", 1, "AUTO_DEEP"),
                        _point("Optional", 2, "OPTIONAL_DEEP"),
                        _point("Brief", 3, "BRIEF_ONLY"),
                    ],
                    "discarded_items": [],
                },
                "scored_articles": [_article("1"), _article("2"), _article("3")],
                "raw_articles": [],
                "history_memories": {},
                "log_history": [],
                "focus": "AI",
                "groups": [],
                "status": "RUNNING",
                "created_at": None,
            }

            write_primary_brief_mock = AsyncMock(
                return_value="# Today Brief\n\n## What Happened\n- Auto\n- Optional\n- Brief\n\n## Today's Pattern\nPattern"
            )
            with patch("agent.workflow.executor.get_article_content", AsyncMock(return_value={})), patch(
                "agent.workflow.executor.write_primary_brief",
                write_primary_brief_mock,
            ):
                executor.handle_summarize = AsyncMock(return_value="## Auto\nDeep analysis.")
                results = await executor.execute(state)

            write_primary_brief_mock.assert_awaited_once_with(client, state["plan"])
            executor.handle_summarize.assert_awaited_once()
            deep_point = executor.handle_summarize.await_args.args[0]
            self.assertEqual(deep_point["topic"], "Auto")
            self.assertEqual(deep_point["generation_mode"], "AUTO_DEEP")
            self.assertIn("# Today Brief", results[0][0])
            self.assertIn("## Deep Analysis", results[0][0])
            self.assertIn("Deep analysis.", results[0][0])
            self.assertIn("## Optional Analysis", results[0][0])
            self.assertIn("Optional happened.", results[0][0])

        asyncio.run(_run_test())

    def test_execute_returns_brief_when_no_auto_deep(self):
        async def _run_test():
            client = MagicMock()
            executor = AgentExecutor(client)
            state = {
                "plan": {
                    "daily_overview": "Overview",
                    "today_pattern": "Pattern",
                    "daily_brief_items": [],
                    "focal_points": [
                        _point("Optional", 1, "OPTIONAL_DEEP"),
                        _point("Brief", 2, "BRIEF_ONLY"),
                    ],
                    "discarded_items": [],
                },
                "scored_articles": [_article("1"), _article("2")],
                "raw_articles": [],
                "history_memories": {},
                "log_history": [],
                "focus": "AI",
                "groups": [],
                "status": "RUNNING",
                "created_at": None,
            }

            write_primary_brief_mock = AsyncMock(
                return_value="# Today Brief\n\n## What Happened\n- Optional\n- Brief\n\n## Today's Pattern\nPattern"
            )
            with patch("agent.workflow.executor.get_article_content", AsyncMock(return_value={})), patch(
                "agent.workflow.executor.write_primary_brief",
                write_primary_brief_mock,
            ):
                executor.handle_summarize = AsyncMock(return_value="This must not be called.")
                results = await executor.execute(state)

            write_primary_brief_mock.assert_awaited_once_with(client, state["plan"])
            executor.handle_summarize.assert_not_called()
            self.assertTrue(results[0][0].startswith("# Today Brief"))
            self.assertIn("## Optional Analysis", results[0][0])

        asyncio.run(_run_test())


class WorkflowOverviewTest(unittest.TestCase):
    def test_workflow_uses_today_pattern_as_overview(self):
        from agent.workflow import SummarizeAgenticWorkflow

        workflow = SummarizeAgenticWorkflow(lazy_init=True)
        plan = {
            "daily_overview": "Old overview.",
            "today_pattern": "Infrastructure is the main signal today.",
        }

        self.assertEqual(workflow._extract_overview(plan), "Infrastructure is the main signal today.")

    def test_workflow_falls_back_to_daily_overview(self):
        from agent.workflow import SummarizeAgenticWorkflow

        workflow = SummarizeAgenticWorkflow(lazy_init=True)
        plan = {"daily_overview": "Old overview."}

        self.assertEqual(workflow._extract_overview(plan), "Old overview.")

    def test_workflow_returns_empty_for_none_plan(self):
        from agent.workflow import SummarizeAgenticWorkflow

        workflow = SummarizeAgenticWorkflow(lazy_init=True)
        self.assertEqual(workflow._extract_overview(None), "")


if __name__ == "__main__":
    unittest.main()
