"""数据库工具函数模块

提供数据库相关的工具函数。
"""

from typing import Tuple, List
import logging

from core.db.pool import get_async_connection
from core.models.feed import FeedGroup, Feed
from agent.models import RawArticle
from core.embedding import (
    embed_text,
    is_embedding_configured,
    EmbeddingError,
)

logger = logging.getLogger(__name__)

# Focus 相似度阈值：0.85 表示 85% 相似度以上才视为相同 focus
# 例如 "AI安全" 和 "人工智能安全" 的相似度通常 > 0.85
FOCUS_SIMILARITY_THRESHOLD = 0.85


async def get_recent_group_update(
    hour_gap: int, group_ids: list[int], focus: str = ""
) -> Tuple[List[FeedGroup], List[RawArticle]]:
    """获取最近更新的分组及其文章

    从数据库中获取指定分组在指定时间范围内的最新文章。
    该函数会自动过滤掉已经被处理过的文章（通过 excluded_feed_item_ids 表），
    但排除是基于 focus（关注点）级别的，同一篇文章可以在不同的 focus 下重复使用。

    Args:
        hour_gap: 时间范围，以小时为单位。例如 hour_gap=24 表示获取过去24小时内的文章
        group_ids: 要查询的分组ID列表
        focus: 用户关注点/主题，用于排除粒度控制

    Returns:
        (分组列表, 文章列表) 元组
    """
    if not group_ids:
        return [], []

    if hour_gap <= 0:
        raise ValueError("hour_gap 必须大于 0")

    # 确保 focus 不为 None
    focus = focus or ""

    use_vector_match = False
    focus_embedding = None
    if focus and is_embedding_configured():
        try:
            focus_embedding = await embed_text(focus)
            use_vector_match = True
            logger.debug(f"Using vector similarity matching for focus: {focus}")
        except EmbeddingError as e:
            logger.warning(
                f"Failed to generate focus embedding, falling back to string matching: {e}"
            )
            use_vector_match = False

    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            # 查询 1: 获取 groups
            await cur.execute(
                """SELECT id, title, "desc" FROM feed_groups WHERE id = ANY(%s)""",
                (group_ids,),
            )
            group_rows = await cur.fetchall()
            groups = [
                FeedGroup(id=row[0], title=row[1], desc=row[2])
                for row in group_rows
            ]

            if not groups:
                return [], []

            # 查询 2: 获取文章数据
            # 排除逻辑：只排除在相同或相似 focus 下已使用的文章
            # 支持向量相似度匹配（如果配置了 embedding）："AI安全" ≈ "人工智能安全"
            # 否则回退到字符串精确匹配
            if use_vector_match and focus_embedding:
                # 使用向量相似度匹配：排除相似度 >= 阈值的 focus
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
                                -- 向量相似度匹配：相似度 >= 阈值
                                (efi.focus_embedding IS NOT NULL 
                                 AND 1 - (efi.focus_embedding <=> %s::vector) >= %s)
                                OR
                                -- 字符串精确匹配（作为后备，处理没有 embedding 的历史记录）
                                (efi.focus_embedding IS NULL AND efi.focus = %s)
                            )
                      );
                    """,
                    (
                        group_ids, hour_gap, group_ids, group_ids, hour_gap,
                        focus_embedding, FOCUS_SIMILARITY_THRESHOLD, focus
                    ),
                )
            else:
                # 回退到字符串精确匹配
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
    """获取所有订阅源

    获取系统中所有可用的订阅源列表。
    每个订阅源包含 id、title、url、description 等信息，用于了解可用的信息源。

    Returns:
        订阅源列表
    """
    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT id, title, url, last_updated, description, status FROM feeds ORDER BY id ASC"""
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
    hour_gap: int, feed_ids: list[int]
) -> Tuple[List[Feed], List[RawArticle]]:
    """获取最近更新的订阅源及其文章

    从数据库中获取指定订阅源在指定时间范围内的最新文章摘要。
    返回的 articles 只包含摘要信息（id、title、url、summary、pub_date），不包含全文内容。
    如果需要获取文章的完整内容，请使用 get_article_content 函数。
    注意：此函数不会过滤已处理过的文章，会返回所有符合条件的文章。

    Args:
        hour_gap: 时间范围，以小时为单位
        feed_ids: 要查询的订阅源ID列表

    Returns:
        (订阅源列表, 文章列表) 元组
    """
    if not feed_ids:
        return [], []

    if hour_gap <= 0:
        raise ValueError("hour_gap 必须大于 0")

    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            # 查询 1: 获取 feeds
            await cur.execute(
                """SELECT id, title, url, last_updated, description, status FROM feeds WHERE id = ANY(%s)""",
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

            # 查询 2: 获取文章摘要（不包含全文内容，避免上下文窗口被挤爆）
            await cur.execute(
                """
                SELECT
                    fi.id, fi.title, fi.link, fi.summary, fi.pub_date
                FROM feed_items fi
                WHERE fi.feed_id = ANY(%s)
                  AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                ORDER BY fi.pub_date DESC;
                """,
                (feed_ids, hour_gap),
            )

            item_rows = await cur.fetchall()
            items = [
                RawArticle(
                    id=str(row[0]),
                    title=row[1],
                    url=row[2],
                    summary=row[3] or "",
                    pub_date=row[4],
                    # 不包含 content 字段，只返回摘要
                )
                for row in item_rows
            ]

            return feeds, items


async def get_article_content(article_ids: list[str]) -> dict[str, str]:
    """获取指定文章的完整内容

    根据文章ID列表获取这些文章的完整内容。
    返回一个字典，key 是文章ID（字符串），value 是文章的完整内容（字符串）。
    如果某个文章ID不存在或没有内容，该ID对应的值为空字符串。
    建议只在需要详细内容时才调用此函数，避免上下文窗口过大。

    Args:
        article_ids: 文章ID列表

    Returns:
        字典，key 是文章ID（字符串），value 是文章内容（字符串）
    """
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
            # 构建字典，key 是字符串ID，value 是内容
            result = {str(row[0]): (row[1] or "") for row in rows}

            # 确保所有请求的 ID 都在结果中（不存在的设为空字符串）
            for aid in article_ids:
                if aid not in result:
                    result[aid] = ""

            return result
