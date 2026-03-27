"""数据库工具函数模块

提供数据库相关的工具函数。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from agent.models import RawArticle
from agent.tools.constants import (
    DEFAULT_FEED_CANDIDATE_LIMIT,
    FOCUS_SIMILARITY_THRESHOLD,
    MAX_FEED_CANDIDATE_LIMIT,
)
from core.db.pool import get_async_connection
from core.embedding import (
    EmbeddingError,
    embed_text,
    is_embedding_configured,
)
from core.models.feed import Feed, FeedGroup

logger = logging.getLogger(__name__)

def _build_query_patterns(query: str) -> list[str]:
    tokens = [token.strip() for token in query.split() if token.strip()]
    if not tokens:
        return []
    return [f"%{token}%" for token in tokens]


async def get_recent_group_update(
    hour_gap: int, group_ids: list[int], focus: str = ""
) -> Tuple[List[FeedGroup], List[RawArticle]]:
    """获取最近更新的分组及其文章

    从数据库中获取指定分组在指定时间范围内的最新文章。
    该函数会自动过滤掉已经被处理过的文章（通过 excluded_feed_item_ids 表），
    但排除是基于 focus（关注点）级别的，同一篇文章可以在不同的 focus 下重复使用。
    """
    if not group_ids:
        return [], []

    if hour_gap <= 0:
        raise ValueError("hour_gap 必须大于 0")

    focus = focus or ""

    use_vector_match = False
    focus_embedding = None
    if focus and is_embedding_configured():
        try:
            focus_embedding = await embed_text(focus)
            use_vector_match = True
            logger.debug("Using vector similarity matching for focus: %s", focus)
        except EmbeddingError as e:
            logger.warning(
                "Failed to generate focus embedding, falling back to string matching: %s", e
            )
            use_vector_match = False

    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                'SELECT id, title, "desc" FROM feed_groups WHERE id = ANY(%s)',
                (group_ids,),
            )
            group_rows = await cur.fetchall()
            groups = [
                FeedGroup(id=row[0], title=row[1], desc=row[2])
                for row in group_rows
            ]

            if not groups:
                return [], []

            if use_vector_match and focus_embedding:
                await cur.execute(
                    """
                    SELECT
                        fi.id, fi.title, fi.link, fi.summary, fi.pub_date,
                        fic.content
                    FROM feed_items fi
                    JOIN feed_group_items fgi ON fgi.feed_id = fi.feed_id
                    JOIN feed_item_contents fic ON fic.feed_item_id = fi.id
                    WHERE fgi.feed_group_id = ANY(%s)
                      AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM excluded_feed_item_ids efi
                          WHERE efi.item_id = fi.id
                            AND efi.group_ids @> %s::integer[] AND efi.group_ids <@ %s::integer[]
                            AND efi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                            AND (
                                (efi.focus_embedding IS NOT NULL
                                 AND 1 - (efi.focus_embedding <=> %s::vector) >= %s)
                                OR
                                (efi.focus_embedding IS NULL AND efi.focus = %s)
                            )
                      );
                    """,
                    (
                        group_ids,
                        hour_gap,
                        group_ids,
                        group_ids,
                        hour_gap,
                        focus_embedding,
                        FOCUS_SIMILARITY_THRESHOLD,
                        focus,
                    ),
                )
            else:
                await cur.execute(
                    """
                    SELECT
                        fi.id, fi.title, fi.link, fi.summary, fi.pub_date,
                        fic.content
                    FROM feed_items fi
                    JOIN feed_group_items fgi ON fgi.feed_id = fi.feed_id
                    JOIN feed_item_contents fic ON fic.feed_item_id = fi.id
                    WHERE fgi.feed_group_id = ANY(%s)
                      AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM excluded_feed_item_ids efi
                          WHERE efi.item_id = fi.id
                            AND efi.focus = %s
                            AND efi.group_ids @> %s::integer[] AND efi.group_ids <@ %s::integer[]
                            AND efi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                      );
                    """,
                    (group_ids, hour_gap, focus, group_ids, group_ids, hour_gap),
                )

            item_rows = await cur.fetchall()
            items = [
                RawArticle(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    summary=row[3],
                    pub_date=row[4],
                    content=row[5],
                )
                for row in item_rows
            ]

            return groups, items


async def get_all_feeds() -> List[Feed]:
    """获取所有订阅源。"""
    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, title, url, last_updated, description, status FROM feeds ORDER BY id ASC"
            )
            rows = await cur.fetchall()
            feeds = [
                Feed(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    last_updated=row[3],
                    desc=row[4] or "",
                    status=row[5] or "active",
                )
                for row in rows
            ]
            return feeds


async def get_recent_feed_update(
    hour_gap: int,
    feed_ids: list[int],
    query: str = "",
    candidate_limit: int = 0,
    use_vector_prefilter: bool = True,
) -> Tuple[List[Feed], List[RawArticle]]:
    """获取最近更新的订阅源及其文章（支持 query 粗筛）。"""
    if not feed_ids:
        return [], []

    if hour_gap <= 0:
        raise ValueError("hour_gap 必须大于 0")

    query = (query or "").strip()
    if candidate_limit <= 0:
        candidate_limit = DEFAULT_FEED_CANDIDATE_LIMIT if query else 0
    candidate_limit = min(max(candidate_limit, 1), MAX_FEED_CANDIDATE_LIMIT)

    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, title, url, last_updated, description, status FROM feeds WHERE id = ANY(%s)",
                (feed_ids,),
            )
            feed_rows = await cur.fetchall()
            feeds = [
                Feed(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    last_updated=row[3],
                    desc=row[4] or "",
                    status=row[5] or "active",
                )
                for row in feed_rows
            ]

            if not feeds:
                return [], []

            item_rows = []
            used_vector_prefilter = False

            if query and use_vector_prefilter and is_embedding_configured():
                try:
                    query_embedding = await embed_text(query)
                    await cur.execute(
                        """
                        SELECT
                            fi.id, fi.title, fi.link, fi.summary, fi.pub_date,
                            1 - (COALESCE(fi.summary_embedding, fi.title_embedding) <=> %s::vector) AS semantic_prefilter_score
                        FROM feed_items fi
                        WHERE fi.feed_id = ANY(%s)
                          AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                          AND COALESCE(fi.summary_embedding, fi.title_embedding) IS NOT NULL
                        ORDER BY COALESCE(fi.summary_embedding, fi.title_embedding) <=> %s::vector ASC,
                                 fi.pub_date DESC
                        LIMIT %s
                        """,
                        (
                            query_embedding,
                            feed_ids,
                            hour_gap,
                            query_embedding,
                            candidate_limit,
                        ),
                    )
                    item_rows = await cur.fetchall()
                    used_vector_prefilter = True
                except Exception as exc:
                    logger.warning(
                        "Vector prefilter unavailable, fallback to lexical prefilter: %s",
                        exc,
                    )

            if query and not item_rows:
                patterns = _build_query_patterns(query)
                if patterns:
                    await cur.execute(
                        """
                        SELECT
                            fi.id, fi.title, fi.link, fi.summary, fi.pub_date
                        FROM feed_items fi
                        WHERE fi.feed_id = ANY(%s)
                          AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                          AND (
                                fi.title ILIKE ANY(%s)
                                OR fi.summary ILIKE ANY(%s)
                          )
                        ORDER BY fi.pub_date DESC
                        LIMIT %s
                        """,
                        (feed_ids, hour_gap, patterns, patterns, candidate_limit),
                    )
                    item_rows = await cur.fetchall()

            if not item_rows:
                if query:
                    await cur.execute(
                        """
                        SELECT
                            fi.id, fi.title, fi.link, fi.summary, fi.pub_date
                        FROM feed_items fi
                        WHERE fi.feed_id = ANY(%s)
                          AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                        ORDER BY fi.pub_date DESC
                        LIMIT %s
                        """,
                        (feed_ids, hour_gap, candidate_limit),
                    )
                else:
                    if candidate_limit > 0:
                        await cur.execute(
                            """
                            SELECT
                                fi.id, fi.title, fi.link, fi.summary, fi.pub_date
                            FROM feed_items fi
                            WHERE fi.feed_id = ANY(%s)
                              AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                            ORDER BY fi.pub_date DESC
                            LIMIT %s
                            """,
                            (feed_ids, hour_gap, candidate_limit),
                        )
                    else:
                        await cur.execute(
                            """
                            SELECT
                                fi.id, fi.title, fi.link, fi.summary, fi.pub_date
                            FROM feed_items fi
                            WHERE fi.feed_id = ANY(%s)
                              AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                            ORDER BY fi.pub_date DESC
                            """,
                            (feed_ids, hour_gap),
                        )
                item_rows = await cur.fetchall()

            items = []
            for row in item_rows:
                article = RawArticle(
                    id=str(row[0]),
                    title=row[1],
                    url=row[2],
                    summary=row[3] or "",
                    pub_date=row[4],
                )
                if len(row) > 5 and row[5] is not None:
                    article["semantic_prefilter_score"] = float(row[5])
                items.append(article)

            logger.info(
                "[db:get_recent_feed_update] query=%s hour_gap=%s limit=%s rows=%d vector_prefilter=%s",
                query,
                hour_gap,
                candidate_limit,
                len(items),
                used_vector_prefilter,
            )
            return feeds, items


async def get_article_content(article_ids: list[str]) -> dict[str, str]:
    """获取指定文章的完整内容。"""
    if not article_ids:
        return {}

    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    fi.id, fic.content
                FROM feed_items fi
                JOIN feed_item_contents fic ON fic.feed_item_id = fi.id
                WHERE fi.id = ANY(%s);
                """,
                (article_ids,),
            )

            rows = await cur.fetchall()
            result = {str(row[0]): (row[1] or "") for row in rows}

            for aid in article_ids:
                if aid not in result:
                    result[aid] = ""

            return result
