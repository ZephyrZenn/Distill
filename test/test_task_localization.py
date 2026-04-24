import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.models import log_step
from agent.tracing import trace_event
from agent.workflow import SummarizeAgenticWorkflow
from apps.backend.router.brief import router


class GenerateBriefRouterLocalizationTest(unittest.TestCase):
    def test_generate_brief_passes_ui_language_to_task_service(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with (
            patch(
                "apps.backend.router.brief.task_service.create_task",
                return_value="task-123",
            ) as create_task,
            patch(
                "apps.backend.router.brief.task_service.execute_brief_generation_task",
                AsyncMock(return_value=None),
            ),
        ):
            response = client.post(
                "/briefs/generate",
                json={
                    "group_ids": [1],
                    "focus": "AI market",
                    "agent_mode": False,
                    "ui_language": "en",
                },
            )

        self.assertEqual(response.status_code, 200)
        create_task.assert_called_once_with(
            group_ids=[1],
            focus="AI market",
            agent_mode=False,
            ui_language="en",
        )


class WorkflowLocalizationTest(unittest.IsolatedAsyncioTestCase):
    def test_log_step_renders_structured_event_in_english(self):
        state = {
            "log_history": [],
            "ui_language": "en",
        }

        log_step(state, trace_event("workflow.start", n_articles=3))

        self.assertEqual(state["log_history"], ["🚀 Agent started, fetched 3 articles"])

    async def test_summarize_emits_english_logs_when_ui_language_is_en(self):
        workflow = SummarizeAgenticWorkflow(lazy_init=True)
        workflow._client = MagicMock()
        workflow._planner = MagicMock()
        workflow._executor = MagicMock()
        workflow._planner.plan = AsyncMock(
            return_value={
                "today_pattern": "AI vendors shifted to enterprise distribution.",
                "focal_points": [],
            }
        )
        workflow._executor.execute = AsyncMock(return_value=[("brief body", True)])

        logs: list[str] = []

        with (
            patch(
                "agent.workflow.get_recent_group_update",
                AsyncMock(return_value=([], [])),
            ),
            patch(
                "agent.workflow.save_current_execution_records",
                AsyncMock(return_value=None),
            ),
        ):
            result = await workflow.summarize(
                task_id="task-1",
                hour_gap=24,
                group_ids=[1],
                focus="AI market",
                on_step=logs.append,
                ui_language="en",
            )

        self.assertEqual(result[0], "brief body")
        self.assertIn("🚀 Agent started, fetched 0 articles", logs)
        self.assertIn("📋 Starting planning stage...", logs)
        self.assertIn("⚡ Starting execution stage...", logs)
        self.assertIn("✅ Agent finished, generated 1 article(s)", logs)


if __name__ == "__main__":
    unittest.main()
