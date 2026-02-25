import ast
import asyncio
from datetime import datetime
from pathlib import Path
import unittest

from agent.models import AgentState
from agent.workflow.executor import AgentExecutor
from agent.workflow.planner import AgentPlanner
from agent.workflow.providers import (
    InMemoryWorkflowArticleContentProvider,
    InMemoryWorkflowMemoryProvider,
)
from core.models.feed import FeedGroup


class _FakeLLMClient:
    async def completion(self, prompt):
        # _rank_articles 分支：传入单条 user message
        if isinstance(prompt, list) and len(prompt) == 1:
            return '{"scores":[{"id":"a1","score":8,"reasoning":"hit"}]}'
        # plan 分支
        return (
            '{"daily_overview":"ok","focal_points":[{"priority":1,'
            '"topic":"t","match_type":"FOCUS_MATCH","strategy":"SUMMARIZE",'
            '"article_ids":["a1"],"reasoning":"r","search_query":"",'
            '"writing_guide":"w","relevance_description":"rel",'
            '"history_memory_id":[]}],"discarded_items":[]}'
        )


class _NoLLMExecutor(AgentExecutor):
    async def _write_article(self, writing_material, review=None):
        return "mock-article"

    async def _review_article(self, draft_content, material):
        return {
            "status": "APPROVED",
            "score": 100,
            "findings": [],
            "overall_comment": "ok",
            "decision_logic": "ok",
        }


class WorkflowDBDecouplingTest(unittest.TestCase):
    def test_planner_runs_with_in_memory_provider(self):
        planner = AgentPlanner(
            _FakeLLMClient(),
            memory_provider=InMemoryWorkflowMemoryProvider(
                memories={
                    1: {"id": 1, "topic": "history", "reasoning": "r", "content": "c"}
                }
            ),
        )

        state: AgentState = {
            "focus": "AI",
            "groups": [FeedGroup(id=1, title="g", desc="")],
            "raw_articles": [
                {
                    "id": "a1",
                    "title": "title",
                    "url": "https://example.com",
                    "summary": "summary",
                    "pub_date": datetime.now(),
                }
            ],
            "scored_articles": [],
            "history_memories": {},
            "log_history": [],
            "status": "PENDING",
            "created_at": datetime.now(),
        }

        plan = asyncio.run(planner.plan(state))
        self.assertEqual(plan["focal_points"][0]["article_ids"], ["a1"])
        self.assertIn(1, state["history_memories"])

    def test_executor_runs_with_in_memory_article_content_provider(self):
        executor = _NoLLMExecutor(
            _FakeLLMClient(),
            article_content_provider=InMemoryWorkflowArticleContentProvider(
                article_contents={"a1": "full-content"}
            ),
        )

        state: AgentState = {
            "focus": "AI",
            "groups": [FeedGroup(id=1, title="g", desc="")],
            "raw_articles": [],
            "scored_articles": [
                {
                    "id": "a1",
                    "title": "title",
                    "url": "https://example.com",
                    "summary": "summary",
                    "pub_date": datetime.now(),
                    "score": 8,
                    "reasoning": "r",
                }
            ],
            "history_memories": {},
            "plan": {
                "daily_overview": "",
                "focal_points": [
                    {
                        "priority": 1,
                        "topic": "t",
                        "match_type": "FOCUS_MATCH",
                        "strategy": "SUMMARIZE",
                        "article_ids": ["a1"],
                        "reasoning": "r",
                        "search_query": "",
                        "writing_guide": "w",
                        "relevance_description": "rel",
                        "history_memory_id": [],
                    }
                ],
                "discarded_items": [],
            },
            "log_history": [],
            "status": "PENDING",
            "created_at": datetime.now(),
        }

        result = asyncio.run(executor.execute(state))
        self.assertEqual(result[0][0], "mock-article")
        self.assertTrue(result[0][1])
        self.assertEqual(state["scored_articles"][0]["content"], "full-content")

    def test_workflow_path_has_no_direct_db_tool_imports(self):
        workflow_dir = Path(__file__).resolve().parent.parent / "agent" / "workflow"
        forbidden = {"agent.tools.db_tool", "agent.tools.memory_tool"}

        for py_file in workflow_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                    self.fail(f"Forbidden import {node.module} in {py_file}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden:
                            self.fail(f"Forbidden import {alias.name} in {py_file}")


if __name__ == "__main__":
    unittest.main()
