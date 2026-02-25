import asyncio
from datetime import datetime
import unittest
from unittest.mock import patch

import distill_lib.api as workflow_api


class _FakePlanner:
    def __init__(self, *args, **kwargs):
        pass

    async def plan(self, state):
        state["scored_articles"] = [
            {
                **article,
                "score": 10,
                "reasoning": "mock",
            }
            for article in state["raw_articles"]
        ]
        state["plan"] = {
            "daily_overview": "ok",
            "focal_points": [
                {
                    "priority": 1,
                    "topic": "t",
                    "match_type": "FOCUS_MATCH",
                    "strategy": "SUMMARIZE",
                    "article_ids": [state["scored_articles"][0]["id"]],
                    "reasoning": "r",
                    "search_query": "",
                    "writing_guide": "w",
                    "relevance_description": "rel",
                    "history_memory_id": [],
                }
            ],
            "discarded_items": [],
        }
        return state["plan"]


class _FakeExecutor:
    def __init__(self, *args, **kwargs):
        pass

    async def execute(self, state):
        return [("mock-summary", True)]


class WorkflowLibContractTest(unittest.TestCase):
    def test_run_workflow_from_articles_db_free_contract(self):
        articles = [
            {
                "id": "a1",
                "title": "Title",
                "url": "https://example.com/1",
                "summary": "Summary",
                "pub_date": datetime.now(),
                "content": "Content",
            }
        ]

        with (
            patch.object(workflow_api, "auto_build_client", return_value=object()),
            patch.object(workflow_api, "AgentPlanner", _FakePlanner),
            patch.object(workflow_api, "AgentExecutor", _FakeExecutor),
        ):
            result = asyncio.run(workflow_api.run_workflow_from_articles(articles=articles, focus="AI"))

        self.assertEqual(result.summary, "mock-summary")
        self.assertEqual(result.ext_info, [])
        self.assertEqual(result.article_count, 1)
        self.assertTrue(any("Agent启动" in line for line in result.logs))

    def test_run_workflow_from_opml_db_free_contract(self):
        fake_feed = type("FeedObj", (), {"id": "a1", "title": "t", "url": "https://x", "summary": "s", "pub_date": datetime.now(), "content": "c"})

        with (
            patch.object(workflow_api, "parse_opml", return_value=[]),
            patch.object(workflow_api, "parse_feed", return_value={"f": [fake_feed]}),
            patch.object(workflow_api, "auto_build_client", return_value=object()),
            patch.object(workflow_api, "AgentPlanner", _FakePlanner),
            patch.object(workflow_api, "AgentExecutor", _FakeExecutor),
        ):
            result = asyncio.run(workflow_api.run_workflow_from_opml("<opml></opml>"))

        self.assertEqual(result.summary, "mock-summary")
        self.assertEqual(result.article_count, 1)


if __name__ == "__main__":
    unittest.main()
