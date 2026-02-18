"""
Test suite for SummarizeAgenticWorkflow state cleanup functionality.

Tests cover:
1. clean_completed_tasks - removing completed/failed/expired states
2. start_cleanup_loop - background periodic cleanup
3. stop_cleanup_loop - graceful shutdown of cleanup loop
"""
import asyncio
import unittest
from datetime import datetime, timedelta

from agent.models import AgentState
from agent.workflow import SummarizeAgenticWorkflow
from core.models.feed import FeedGroup


class WorkflowCleanupTest(unittest.TestCase):
    def setUp(self):
        """Create a workflow instance with lazy init to avoid API key requirement."""
        self.workflow = SummarizeAgenticWorkflow(lazy_init=True)

    def _create_mock_state(
        self, status: str, created_at: datetime | None = None
    ) -> AgentState:
        """Helper to create a mock AgentState."""
        if created_at is None:
            created_at = datetime.now()

        return AgentState(
            groups=[],
            raw_articles=[],
            log_history=[],
            focus="",
            status=status,  # type: ignore
            created_at=created_at,
        )

    def test_clean_completed_tasks_removes_completed_states(self):
        """Test that COMPLETED states are removed."""
        # Add states with different statuses
        self.workflow._states["task1"] = self._create_mock_state("COMPLETED")
        self.workflow._states["task2"] = self._create_mock_state("RUNNING")
        self.workflow._states["task3"] = self._create_mock_state("FAILED")
        self.workflow._states["task4"] = self._create_mock_state("PENDING")

        # Run cleanup
        self.workflow.clean_completed_tasks(max_age_hours=12)

        # Verify COMPLETED and FAILED are removed, others remain
        self.assertNotIn("task1", self.workflow._states)
        self.assertIn("task2", self.workflow._states)  # RUNNING
        self.assertNotIn("task3", self.workflow._states)
        self.assertIn("task4", self.workflow._states)  # PENDING

    def test_clean_completed_tasks_removes_expired_states(self):
        """Test that old states are removed regardless of status."""
        now = datetime.now()
        old_time = now - timedelta(hours=15)
        recent_time = now - timedelta(hours=5)

        self.workflow._states["old_task"] = self._create_mock_state("RUNNING", old_time)
        self.workflow._states["new_task"] = self._create_mock_state(
            "RUNNING", recent_time
        )

        # Run cleanup with 12 hour threshold
        self.workflow.clean_completed_tasks(max_age_hours=12)

        # Verify old task is removed, new task remains
        self.assertNotIn("old_task", self.workflow._states)
        self.assertIn("new_task", self.workflow._states)

    def test_clean_completed_tasks_empty_states(self):
        """Test cleanup with empty states dict."""
        # Should not raise error
        self.workflow.clean_completed_tasks(max_age_hours=12)
        self.assertEqual(len(self.workflow._states), 0)

    def test_clean_completed_tasks_all_expired(self):
        """Test cleanup when all tasks are expired."""
        old_time = datetime.now() - timedelta(hours=20)

        self.workflow._states["task1"] = self._create_mock_state("RUNNING", old_time)
        self.workflow._states["task2"] = self._create_mock_state("PENDING", old_time)

        self.workflow.clean_completed_tasks(max_age_hours=12)

        self.assertEqual(len(self.workflow._states), 0)

    def test_clean_completed_tasks_boundary_condition(self):
        """Test cleanup with exactly at threshold time."""
        now = datetime.now()
        # Exactly at the boundary (12 hours old)
        boundary_time = now - timedelta(hours=12)

        self.workflow._states["boundary_task"] = self._create_mock_state(
            "RUNNING", boundary_time
        )

        # Should be removed (created_at < cutoff_time)
        self.workflow.clean_completed_tasks(max_age_hours=12)

        self.assertNotIn("boundary_task", self.workflow._states)

    async def _test_start_cleanup_loop_basic(self):
        """Helper async test for start_cleanup_loop."""
        # Add a completed task
        self.workflow._states["task1"] = self._create_mock_state("COMPLETED")

        # Start cleanup loop with short interval
        await self.workflow.start_cleanup_loop(interval_seconds=0.1, max_age_hours=0)

        # Wait for cleanup to run
        await asyncio.sleep(0.3)

        # Verify task was cleaned up
        self.assertNotIn("task1", self.workflow._states)

        # Stop the loop
        await self.workflow.stop_cleanup_loop()

    def test_start_cleanup_loop_basic(self):
        """Test that cleanup loop removes completed tasks periodically."""
        asyncio.run(self._test_start_cleanup_loop_basic())

    async def _test_start_cleanup_loop_idempotent(self):
        """Helper async test for multiple start calls."""
        # Start loop twice
        await self.workflow.start_cleanup_loop(interval_seconds=1, max_age_hours=12)
        task1 = self.workflow._cleanup_task

        # Second start should not create new task
        await self.workflow.start_cleanup_loop(interval_seconds=1, max_age_hours=12)
        task2 = self.workflow._cleanup_task

        # Should be the same task
        self.assertIs(task1, task2)

        await self.workflow.stop_cleanup_loop()

    def test_start_cleanup_loop_idempotent(self):
        """Test that multiple start calls don't create multiple loops."""
        asyncio.run(self._test_start_cleanup_loop_idempotent())

    async def _test_stop_cleanup_loop(self):
        """Helper async test for stop_cleanup_loop."""
        await self.workflow.start_cleanup_loop(interval_seconds=1, max_age_hours=12)

        # Verify task is running
        self.assertIsNotNone(self.workflow._cleanup_task)
        self.assertFalse(self.workflow._cleanup_task.done())

        # Stop the loop
        await self.workflow.stop_cleanup_loop()

        # Verify task is stopped
        self.assertIsNone(self.workflow._cleanup_task)

    def test_stop_cleanup_loop(self):
        """Test that cleanup loop stops gracefully."""
        asyncio.run(self._test_stop_cleanup_loop())

    async def _test_stop_cleanup_loop_without_start(self):
        """Helper async test for stop without start."""
        # Should not raise error
        await self.workflow.stop_cleanup_loop()
        self.assertIsNone(self.workflow._cleanup_task)

    def test_stop_cleanup_loop_without_start(self):
        """Test stopping loop without starting it."""
        asyncio.run(self._test_stop_cleanup_loop_without_start())

    async def _test_cleanup_loop_continues_after_cleanup(self):
        """Helper async test to verify loop continues running."""
        # Add initial completed task
        self.workflow._states["task1"] = self._create_mock_state("COMPLETED")
        self.workflow._states["task2"] = self._create_mock_state("RUNNING")

        await self.workflow.start_cleanup_loop(interval_seconds=0.1, max_age_hours=12)

        # Wait for first cleanup
        await asyncio.sleep(0.3)
        self.assertNotIn("task1", self.workflow._states)
        self.assertIn("task2", self.workflow._states)

        # Add another completed task
        self.workflow._states["task3"] = self._create_mock_state("COMPLETED")

        # Wait for another cleanup cycle
        await asyncio.sleep(0.3)
        self.assertNotIn("task3", self.workflow._states)

        await self.workflow.stop_cleanup_loop()

    def test_cleanup_loop_continues_after_cleanup(self):
        """Test that cleanup loop continues running after cleanup."""
        asyncio.run(self._test_cleanup_loop_continues_after_cleanup())

    def test_concurrent_cleanup_and_modify(self):
        """Test that cleanup doesn't crash when states are modified concurrently."""
        import threading
        import time

        # Add many states
        for i in range(100):
            self.workflow._states[f"task{i}"] = self._create_mock_state("RUNNING")

        cleanup_called = threading.Event()
        cleanup_done = threading.Event()

        def cleanup_thread():
            cleanup_called.set()
            self.workflow.clean_completed_tasks(max_age_hours=12)
            cleanup_done.set()

        # Start cleanup in thread
        thread = threading.Thread(target=cleanup_thread)
        thread.start()
        cleanup_called.wait()

        # Modify states while cleanup is in progress
        # (This tests that the fix for iteration-while-delete works)
        time.sleep(0.001)  # Small delay to ensure overlap
        for i in range(100, 110):
            self.workflow._states[f"task{i}"] = self._create_mock_state("PENDING")

        cleanup_done.wait()
        thread.join()

        # Verify no errors occurred and states are consistent
        self.assertGreater(len(self.workflow._states), 0)


if __name__ == "__main__":
    unittest.main()
