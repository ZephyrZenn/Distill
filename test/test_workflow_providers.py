import asyncio
import unittest
from datetime import datetime

from agent.models import AgentState
from agent.workflow import SummarizeAgenticWorkflow
from agent.workflow.providers import (
    DBWorkflowDataProvider,
    DBWorkflowPersistenceProvider,
    InMemoryWorkflowDataProvider,
    NoopWorkflowPersistenceProvider,
)
from core.models.feed import FeedGroup


class _FakePlanner:
    async def plan(self, state: AgentState):
        state["plan"] = {"focal_points": [], "daily_overview": "", "discarded_items": []}  # type: ignore
        return state["plan"]


class _FakeExecutor:
    async def execute(self, state: AgentState):
        return [("mock summary", True)]


class _RecordingDataProvider:
    def __init__(self, groups, articles):
        self.groups = groups
        self.articles = articles
        self.calls = []

    async def get_recent_group_update(self, hour_gap, group_ids, focus=""):
        self.calls.append((hour_gap, group_ids, focus))
        return self.groups, self.articles


class _RecordingPersistenceProvider:
    def __init__(self):
        self.saved_states = []

    async def save_current_execution_records(self, state: AgentState):
        self.saved_states.append(state)


class WorkflowProviderTest(unittest.TestCase):
    def test_default_providers_backward_compatible(self):
        workflow = SummarizeAgenticWorkflow(lazy_init=True)
        self.assertIsInstance(workflow._data_provider, DBWorkflowDataProvider)
        self.assertIsInstance(
            workflow._persistence_provider, DBWorkflowPersistenceProvider
        )

    def test_in_memory_noop_providers_for_db_free_runtime(self):
        groups = [FeedGroup(id=1, title="g1", desc="")]
        articles = [
            {
                "id": "a1",
                "title": "title",
                "url": "https://example.com",
                "summary": "s",
                "pub_date": datetime.now(),
                "content": "c",
            }
        ]

        workflow = SummarizeAgenticWorkflow(
            lazy_init=True,
            data_provider=InMemoryWorkflowDataProvider(groups=groups, articles=articles),
            persistence_provider=NoopWorkflowPersistenceProvider(),
        )

        async def run_test():
            workflow._init_client = lambda: None  # type: ignore
            workflow._planner = _FakePlanner()
            workflow._executor = _FakeExecutor()
            result, ext_info = await workflow.summarize(
                task_id="t1",
                hour_gap=24,
                group_ids=[1],
                focus="",
            )
            self.assertEqual(result, "mock summary")
            self.assertEqual(ext_info, [])

        asyncio.run(run_test())

    def test_injected_providers_are_used(self):
        groups = [FeedGroup(id=2, title="g2", desc="")]
        articles = [
            {
                "id": "a2",
                "title": "title2",
                "url": "https://example.com/2",
                "summary": "s2",
                "pub_date": datetime.now(),
                "content": "c2",
            }
        ]
        data_provider = _RecordingDataProvider(groups, articles)
        persistence_provider = _RecordingPersistenceProvider()

        workflow = SummarizeAgenticWorkflow(
            lazy_init=True,
            data_provider=data_provider,
            persistence_provider=persistence_provider,
        )

        async def run_test():
            workflow._init_client = lambda: None  # type: ignore
            workflow._planner = _FakePlanner()
            workflow._executor = _FakeExecutor()

            result, _ = await workflow.summarize(
                task_id="t2",
                hour_gap=12,
                group_ids=[2, 3],
                focus="AI",
            )

            self.assertEqual(result, "mock summary")
            self.assertEqual(data_provider.calls, [(12, [2, 3], "AI")])
            self.assertEqual(len(persistence_provider.saved_states), 1)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
