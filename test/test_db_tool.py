import unittest
from unittest.mock import AsyncMock, patch

from agent.tools import db_tool


class _FakeCursor:
    def __init__(self, fetch_results):
        self._fetch_results = list(fetch_results)
        self.execute_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        self.execute_calls.append((query, params))

    async def fetchall(self):
        if self._fetch_results:
            return self._fetch_results.pop(0)
        return []


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


class DbToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_recent_group_update_vector_prefilter_respects_candidate_limit(self):
        group_rows = [(5, "AI", "desc")]
        item_rows = [
            (101, "t1", "u1", "s1", "2026-04-16", "c1", 0.92),
            (102, "t2", "u2", "s2", "2026-04-16", "c2", 0.88),
        ]
        fake_cursor = _FakeCursor([group_rows, item_rows])
        fake_conn = _FakeConnection(fake_cursor)

        with (
            patch.object(db_tool, "get_async_connection", return_value=fake_conn),
            patch.object(db_tool, "is_embedding_configured", return_value=True),
            patch.object(db_tool, "embed_text", AsyncMock(return_value=[0.1, 0.2])),
        ):
            groups, items = await db_tool.get_recent_group_update(
                hour_gap=24,
                group_ids=[5],
                focus="AI竞争分析",
                candidate_limit=2,
                use_vector_prefilter=True,
            )

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(items), 2)

        # 第一次 execute: 查 group；第二次 execute: 向量粗筛查文章
        self.assertGreaterEqual(len(fake_cursor.execute_calls), 2)
        vector_query, vector_params = fake_cursor.execute_calls[1]
        self.assertIn("ORDER BY COALESCE(fi.summary_embedding, fi.title_embedding)", vector_query)
        self.assertIn("LIMIT %s", vector_query)
        self.assertEqual(vector_params[-1], 2)
        self.assertIn("semantic_prefilter_score", items[0])

