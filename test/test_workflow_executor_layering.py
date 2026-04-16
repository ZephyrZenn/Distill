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
    def test_execute_saves_optional_topics_for_later_expansion(self):
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
                return_value="# Today Brief\n\n## What Happened\n- Optional\n\n## Today's Pattern\nPattern"
            )
            with patch("agent.workflow.executor.get_article_content", AsyncMock(return_value={})), patch(
                "agent.workflow.executor.write_primary_brief",
                write_primary_brief_mock,
            ):
                executor.handle_summarize = AsyncMock(return_value="This must not be called.")
                await executor.execute(state)

            executor.handle_summarize.assert_not_called()
            self.assertEqual(len(state["expandable_topics"]), 1)
            self.assertEqual(state["expandable_topics"][0]["topic"], "Optional")
            self.assertEqual(state["expandable_topics"][0]["articles"][0]["id"], "1")

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
