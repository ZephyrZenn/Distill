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
            "topic_overview": "Enterprise budget planning faces uncertainty from unresolved AI pricing changes.",
        },
    }


class PatchBriefExpansionTest(unittest.TestCase):
    def _make_conn(self, content, expandable_topics, ext_info=None):
        cursor = MagicMock()
        ext_blob = json.dumps(ext_info if ext_info is not None else [])
        cursor.fetchone.return_value = (content, json.dumps(expandable_topics), ext_blob)
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        # Reuse the same cursor for both with-blocks inside the single connection
        conn.__enter__.return_value.cursor.__iter__ = lambda self: iter([MagicMock(__enter__=MagicMock(return_value=cursor))])
        conn.__enter__.return_value.cursor.__next__ = MagicMock(side_effect=StopIteration)
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

    def test_replaces_section_with_expandable_suffix_heading(self):
        content = "# Brief\n\n## AI Pricing（可展开分析）\n\nOld summary.\n\n## Other Topic\n\nOther content."
        expandable_topics = [_expandable_topic()]
        conn, cursor = self._make_conn(content, expandable_topics)

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            _patch_brief_expansion(12, "1-ai-pricing", "## AI Pricing\n\nDeep analysis.")

        update_call = cursor.execute.call_args_list[-1]
        new_content = update_call.args[1][0]
        self.assertIn("Deep analysis.", new_content)
        self.assertNotIn("Old summary.", new_content)
        self.assertNotIn("可展开分析", new_content)
        self.assertIn("## Other Topic", new_content)

    def test_merges_ext_info_when_extra_provided(self):
        content = "## AI Pricing\n\nOld."
        expandable_topics = [_expandable_topic()]
        prior = [{"title": "Existing", "url": "https://a.example", "content": "c", "score": 0.5}]
        conn, cursor = self._make_conn(content, expandable_topics, ext_info=prior)
        extra = [
            {
                "title": "New Hit",
                "url": "https://b.example",
                "content": "body",
                "score": 0.9,
            }
        ]

        with patch("apps.backend.services.brief_service.get_connection", return_value=conn):
            _patch_brief_expansion(12, "1-ai-pricing", "## AI Pricing\n\nNew.", extra_ext_info=extra)

        update_call = cursor.execute.call_args_list[-1]
        self.assertIn("ext_info", update_call.args[0])
        merged = json.loads(update_call.args[1][2])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["title"], "Existing")
        self.assertEqual(merged[1]["title"], "New Hit")


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
            patch_fn.assert_called_once_with(
                12,
                "1-ai-pricing",
                "## AI Pricing\n\nDeep analysis.",
                extra_ext_info=None,
            )

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
