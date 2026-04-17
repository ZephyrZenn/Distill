import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent.tools.memory_tool import save_current_execution_records


class FakeCursor:
    def __init__(self):
        self.calls = []

    async def executemany(self, sql, params):
        self.calls.append((sql, params))


def _point(topic: str, article_id: str):
    return {
        "priority": int(article_id),
        "topic": topic,
        "match_type": "GLOBAL_STRATEGIC",
        "relevance_description": "Important to the market.",
        "strategy": "SUMMARIZE",
        "article_ids": [article_id],
        "reasoning": f"{topic} reasoning",
        "search_query": "",
        "writing_guide": "Explain impact.",
        "history_memory_id": [],
        "generation_mode": "BRIEF_ONLY",
        "brief_summary": f"{topic} happened.",
    }


def _article(article_id: str):
    return {
        "id": article_id,
        "title": f"Article {article_id}",
        "url": f"https://example.com/{article_id}",
        "summary": "Summary",
        "pub_date": "2026-04-16",
        "score": 8,
        "reasoning": "Important",
    }


class LayeredMemoryRecordsTest(unittest.TestCase):
    def test_single_layered_report_saves_records_for_all_focal_points(self):
        async def _run_test():
            cursor = FakeCursor()

            async def run_transaction(callback):
                await callback(cursor)

            state = {
                "focus": "AI",
                "groups": [SimpleNamespace(id=7)],
                "plan": {
                    "daily_overview": "Old overview.",
                    "today_pattern": "Infrastructure is the main signal today.",
                    "focal_points": [
                        _point("Auto", "1"),
                        _point("Optional", "2"),
                        _point("Brief", "3"),
                    ],
                    "discarded_items": [],
                },
                "scored_articles": [_article("1"), _article("2"), _article("3")],
                "summary_results": ["# Today Brief\n\n## What Happened\n- All three topics."],
                "execution_status": [True],
                "raw_articles": [],
                "history_memories": {},
                "log_history": [],
                "status": "RUNNING",
                "created_at": None,
            }

            with patch("agent.tools.memory_tool.is_embedding_configured", return_value=False), patch(
                "agent.tools.memory_tool.execute_async_transaction",
                AsyncMock(side_effect=run_transaction),
            ):
                await save_current_execution_records(state)

            self.assertEqual(len(cursor.calls), 2)
            excluded_params = cursor.calls[0][1]
            memory_params = cursor.calls[1][1]

            self.assertEqual([row[0] for row in excluded_params], ["1", "2", "3"])
            self.assertEqual(len(memory_params), 1)
            self.assertEqual(memory_params[0][0], "Infrastructure is the main signal today.")
            self.assertEqual(memory_params[0][2], state["summary_results"][0])

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
