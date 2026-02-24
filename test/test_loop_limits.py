"""Unit tests for loop limiting circuit breakers in Plan & Solve Agent."""

import unittest
from agent.ps_agent.state import create_initial_state, check_layer1_limits
from agent.ps_agent.graph import curation_router, plan_review_router, summary_review_router


class TestLoopLimits(unittest.TestCase):
    """Test cases for loop limiting functionality."""

    def test_curation_router_max_iterations(self):
        """Test that curation_router forces to plan_review when max_iterations hit."""
        state = create_initial_state("test focus", max_iterations=3)
        state["iteration"] = 3  # At limit
        state["ready_for_review"] = False

        route = curation_router(state)
        self.assertEqual(route, "plan_review", "Should route to plan_review when max_iterations hit")

    def test_curation_router_normal_flow(self):
        """Test that curation_router continues research when under limits."""
        state = create_initial_state("test focus", max_iterations=10)
        state["iteration"] = 3  # Under limit
        state["ready_for_review"] = False

        route = curation_router(state)
        self.assertEqual(route, "research", "Should continue research when under limits")

    def test_curation_router_ready_for_review(self):
        """Test that curation_router respects ready_for_review flag."""
        state = create_initial_state("test focus", max_iterations=10)
        state["iteration"] = 3  # Under limit
        state["ready_for_review"] = True  # Normal exit

        route = curation_router(state)
        self.assertEqual(route, "plan_review", "Should route to plan_review when ready_for_review=True")

    def test_curation_router_max_tool_calls(self):
        """Test that curation_router forces to plan_review when max_tool_calls hit."""
        state = create_initial_state("test focus", max_tool_calls=20)
        state["tool_call_count"] = 20  # At limit
        state["ready_for_review"] = False

        route = curation_router(state)
        self.assertEqual(route, "plan_review", "Should route to plan_review when max_tool_calls hit")

    def test_curation_router_max_curations(self):
        """Test that curation_router forces to plan_review when max_curations hit."""
        state = create_initial_state("test focus", max_curations=5)
        state["curation_count"] = 5  # At limit
        state["ready_for_review"] = False

        route = curation_router(state)
        self.assertEqual(route, "plan_review", "Should route to plan_review when max_curations hit")

    def test_plan_review_router_max_reviews(self):
        """Test that plan_review_router forces to structure when max_plan_reviews hit."""
        state = create_initial_state("test focus", max_plan_reviews=2)
        state["plan_review_count"] = 2  # At limit
        state["ready_for_write"] = False
        state["execution_mode"] = "NORMAL"

        route = plan_review_router(state)
        self.assertEqual(route, "structure", "Should route to structure when max_plan_reviews hit")

    def test_plan_review_router_ready_for_write(self):
        """Test that plan_review_router respects ready_for_write flag."""
        state = create_initial_state("test focus", max_plan_reviews=5)
        state["plan_review_count"] = 2  # Under limit
        state["ready_for_write"] = True  # Normal exit

        route = plan_review_router(state)
        self.assertEqual(route, "structure", "Should route to structure when ready_for_write=True")

    def test_plan_review_router_replan_mode(self):
        """Test that plan_review_router respects REPLAN_MODE when under limits."""
        state = create_initial_state("test focus", max_plan_reviews=5)
        state["plan_review_count"] = 2  # Under limit
        state["ready_for_write"] = False
        state["execution_mode"] = "REPLAN_MODE"

        route = plan_review_router(state)
        self.assertEqual(route, "bootstrap", "Should route to bootstrap when REPLAN_MODE and under limits")

    def test_plan_review_router_replan_mode_blocked_by_limit(self):
        """Test that plan_review_router ignores REPLAN_MODE when limit hit."""
        state = create_initial_state("test focus", max_plan_reviews=2)
        state["plan_review_count"] = 2  # At limit
        state["ready_for_write"] = False
        state["execution_mode"] = "REPLAN_MODE"

        route = plan_review_router(state)
        self.assertEqual(route, "structure", "Should route to structure when limit hit, ignoring REPLAN_MODE")

    def test_summary_review_router_max_refines(self):
        """Test that summary_review_router forces to completed when max_refines hit."""
        state = create_initial_state("test focus", max_refines=2)
        state["refine_count"] = 2  # At limit
        state["status"] = "refining"  # Not completed

        route = summary_review_router(state)
        self.assertEqual(route, "completed", "Should route to completed when max_refines hit")

    def test_summary_review_router_completed(self):
        """Test that summary_review_router respects completed status."""
        state = create_initial_state("test focus", max_refines=5)
        state["refine_count"] = 2  # Under limit
        state["status"] = "completed"  # Normal exit

        route = summary_review_router(state)
        self.assertEqual(route, "completed", "Should route to completed when status=completed")

    def test_summary_review_router_normal_flow(self):
        """Test that summary_review_router continues refining when under limits."""
        state = create_initial_state("test focus", max_refines=5)
        state["refine_count"] = 2  # Under limit
        state["status"] = "refining"  # Not completed

        route = summary_review_router(state)
        self.assertEqual(route, "refining", "Should continue refining when under limits and not completed")

    def test_layer1_hard_limit_check(self):
        """Test Layer 1 hard limit detection."""
        state = create_initial_state("test focus", max_iterations=5)

        # Under limit
        should_fail, reason = check_layer1_limits(state, "iteration", 3)
        self.assertFalse(should_fail, "Should not fail under limit")
        self.assertIsNone(reason, "Reason should be None under limit")

        # At limit
        should_fail, reason = check_layer1_limits(state, "iteration", 5)
        self.assertTrue(should_fail, "Should fail at limit")
        self.assertIn("iteration=5 >= max_iterations=5", reason, "Reason should describe the limit")

        # Over limit
        should_fail, reason = check_layer1_limits(state, "iteration", 6)
        self.assertTrue(should_fail, "Should fail over limit")
        self.assertIn("iteration=6 >= max_iterations=5", reason, "Reason should describe the limit")

    def test_layer1_hard_limit_disabled(self):
        """Test that Layer 1 can be disabled via enable_hard_limits."""
        state = create_initial_state("test focus", max_iterations=5)
        state["enable_hard_limits"] = False  # Disable Layer 1

        # Should not fail even at limit
        should_fail, reason = check_layer1_limits(state, "iteration", 10)
        self.assertFalse(should_fail, "Should not fail when Layer 1 disabled")
        self.assertIsNone(reason, "Reason should be None when Layer 1 disabled")

    def test_layer1_all_counter_types(self):
        """Test Layer 1 limit checking for all counter types."""
        state = create_initial_state(
            "test focus",
            max_iterations=5,
            max_tool_calls=20,
            max_curations=8,
            max_plan_reviews=3,
            max_refines=3,
        )

        # Test each counter type
        counters = [
            ("iteration", 5),
            ("tool_call_count", 20),
            ("curation_count", 8),
            ("plan_review_count", 3),
            ("refine_count", 3),
        ]

        for counter_name, limit_value in counters:
            should_fail, reason = check_layer1_limits(state, counter_name, limit_value)
            self.assertTrue(should_fail, f"Should fail for {counter_name} at limit")
            self.assertIn(counter_name, reason, f"Reason should mention {counter_name}")

    def test_layer1_unknown_counter(self):
        """Test Layer 1 with unknown counter name."""
        state = create_initial_state("test focus")
        should_fail, reason = check_layer1_limits(state, "unknown_counter", 100)
        self.assertFalse(should_fail, "Should not fail for unknown counter")
        self.assertIsNone(reason, "Reason should be None for unknown counter")

    def test_multiple_limits_hit(self):
        """Test router behavior when multiple limits are hit simultaneously."""
        state = create_initial_state(
            "test focus",
            max_iterations=5,
            max_tool_calls=10,
            max_curations=3,
        )
        state["iteration"] = 5  # At limit
        state["tool_call_count"] = 10  # At limit
        state["curation_count"] = 3  # At limit
        state["ready_for_review"] = False

        # Should still route to plan_review (first limit hit)
        route = curation_router(state)
        self.assertEqual(route, "plan_review", "Should route to plan_review when multiple limits hit")


if __name__ == "__main__":
    unittest.main()
