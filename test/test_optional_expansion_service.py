import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.backend.services.brief_service import _patch_brief_expansion, expand_optional_topic


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
    }


class PatchBriefExpansionTest(unittest.TestCase):
    def _make_conn(self, content, expandable_topics):
        cursor = MagicMock()
        cursor.fetchone.return_value = (content, json.dumps(expandable_topics))
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        return conn, cursor

    def test_replaces_section_under_matching_heading(self):
        content = "# Brief\n\n## AI Pricing\n\nOld summary.\n\n## Other Topic\n\nOther content."
        expandable_topics = [_expandable_topic()]
        conn, cursor = self._make_conn(content, expandable_topics)

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            _patch_brief_expansion(12, "1-ai-pricing", "## AI Pricing\n\nDeep analysis.")

        update_call = cursor.execute.call_args_list[-1]
        new_content = update_call.args[1][0]
        self.assertIn("Deep analysis.", new_content)
        self.assertNotIn("Old summary.", new_content)
        self.assertIn("## Other Topic", new_content)

    def test_removes_topic_from_expandable_topics(self):
        content = "## AI Pricing\n\nOld summary."
        expandable_topics = [_expandable_topic(), {"topic_id": "2-other", "focal_point": {"topic": "Other"}}]
        conn, cursor = self._make_conn(content, expandable_topics)

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            _patch_brief_expansion(12, "1-ai-pricing", "## AI Pricing\n\nDeep analysis.")

        update_call = cursor.execute.call_args_list[-1]
        new_topics = json.loads(update_call.args[1][1])
        self.assertEqual(len(new_topics), 1)
        self.assertEqual(new_topics[0]["topic_id"], "2-other")

    def test_appends_when_heading_not_found(self):
        content = "# Brief\n\nSome content."
        expandable_topics = [_expandable_topic()]
        conn, cursor = self._make_conn(content, expandable_topics)

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            _patch_brief_expansion(12, "1-ai-pricing", "## AI Pricing\n\nDeep analysis.")

        update_call = cursor.execute.call_args_list[-1]
        new_content = update_call.args[1][0]
        self.assertIn("Deep analysis.", new_content)
        self.assertIn("Some content.", new_content)


class ExpandOptionalTopicTest(unittest.TestCase):
    def test_fetches_articles_and_patches_brief(self):
        async def _run():
            brief = MagicMock()
            brief.expandable_topics = [_expandable_topic()]
            client = MagicMock()

            with patch("apps.backend.services.brief_service.get_brief_by_id", return_value=brief), \
                 patch("apps.backend.services.brief_service.auto_build_client", return_value=client), \
                 patch("agent.tools.get_article_content", AsyncMock(return_value={"1": "Full content."})) as fetch, \
                 patch("agent.workflow.executor.AgentExecutor.handle_summarize", AsyncMock(return_value="## AI Pricing\n\nDeep analysis.")) as writer, \
                 patch("apps.backend.services.brief_service._patch_brief_expansion") as patch_fn:
                await expand_optional_topic(12, "1-ai-pricing")

            fetch.assert_awaited_once_with(["1"])
            writer.assert_awaited_once()
            patch_fn.assert_called_once_with(12, "1-ai-pricing", "## AI Pricing\n\nDeep analysis.")

        asyncio.run(_run())

    def test_raises_lookup_error_for_missing_topic(self):
        async def _run():
            brief = MagicMock()
            brief.expandable_topics = [_expandable_topic()]
            with patch("apps.backend.services.brief_service.get_brief_by_id", return_value=brief):
                with self.assertRaises(LookupError):
                    await expand_optional_topic(12, "missing-topic")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
