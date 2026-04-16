import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.backend.services.brief_service import expand_optional_topic


def _expandable_topic(strategy: str = "SUMMARIZE"):
    return {
        "topic_id": "1-ai-pricing",
        "focal_point": {
            "priority": 1,
            "topic": "AI Pricing",
            "match_type": "GLOBAL_STRATEGIC",
            "relevance_description": "Pricing affects enterprise adoption.",
            "strategy": strategy,
            "article_ids": ["1"],
            "reasoning": "Budget risk is unresolved.",
            "search_query": "AI pricing enterprise budget",
            "writing_guide": "Explain budget and roadmap impact.",
            "history_memory_id": [],
            "generation_mode": "OPTIONAL_DEEP",
            "brief_summary": "AI pricing changed.",
            "why_expand": "Unresolved budget impact affects roadmap decisions.",
        },
        "articles": [
            {
                "id": "1",
                "title": "AI Pricing",
                "url": "https://example.com/1",
                "summary": "Pricing changed.",
                "pub_date": "2026-04-16",
                "score": 9,
                "reasoning": "Important.",
            }
        ],
    }


class OptionalExpansionServiceTest(unittest.TestCase):
    def test_expand_optional_topic_generates_deep_analysis_from_saved_payload(self):
        async def _run_test():
            brief = MagicMock()
            brief.expandable_topics = [_expandable_topic()]
            client = MagicMock()

            with patch("apps.backend.services.brief_service.get_brief_by_id", return_value=brief), patch(
                "apps.backend.services.brief_service.auto_build_client",
                return_value=client,
            ), patch(
                "agent.tools.get_article_content",
                AsyncMock(return_value={"1": "Full article content."}),
            ) as fetch_content:
                with patch("agent.workflow.executor.AgentExecutor.handle_summarize", AsyncMock(return_value="## AI Pricing\nDeep analysis.")) as writer:
                    result = await expand_optional_topic(12, "1-ai-pricing")

            self.assertEqual(result["topic_id"], "1-ai-pricing")
            self.assertIn("Deep analysis.", result["content"])
            writer.assert_awaited_once()
            fetch_content.assert_awaited_once_with(["1"])

        import asyncio

        asyncio.run(_run_test())

    def test_expand_optional_topic_raises_lookup_error_for_missing_topic(self):
        async def _run_test():
            brief = MagicMock()
            brief.expandable_topics = [_expandable_topic()]
            with patch("apps.backend.services.brief_service.get_brief_by_id", return_value=brief):
                with self.assertRaises(LookupError):
                    await expand_optional_topic(12, "missing-topic")

        import asyncio

        asyncio.run(_run_test())


if __name__ == "__main__":
    unittest.main()
