"""记忆工具函数模块

提供记忆相关的工具函数，包括保存执行记录、搜索历史记忆等。
"""

import logging
from typing import Sequence

from psycopg.rows import dict_row

from agent.models import AgentState, SummaryMemory
from core.db.pool import execute_async_transaction, get_async_connection
from core.embedding import (
    embed_text,
    embed_texts,
    is_embedding_configured,
    EmbeddingError,
)

logger = logging.getLogger(__name__)

SUMMARY_EMBEDDING_MAX_LENGTH = 300


async def save_current_execution_records(state: AgentState) -> None:
    """保存当前执行记录

    将 Agent 的执行记录持久化到数据库。包括两部分数据：
    1. 已处理的文章ID列表 - 存入 excluded_feed_item_ids 表，防止后续重复处理
    2. 生成的摘要记忆 - 存入 summary_memories 表，作为历史知识供后续查询
    3. 如果配置了 embedding 服务，会同时生成并存储向量嵌入用于语义搜索

    Args:
        state: Agent 的完整状态对象，包含 raw_articles、plan.focal_points、summary_results
    """

    # 获取 focus，用于排除粒度控制
    focus = state.get("focus", "") or ""

    # 生成 focus 的 embedding（如果配置了 embedding 服务且 focus 不为空）
    focus_embedding = None
    if focus and is_embedding_configured():
        try:
            focus_embedding = await embed_text(focus)
            logger.debug(f"Generated focus embedding for: {focus}")
        except EmbeddingError as e:
            logger.warning(
                f"Failed to generate focus embedding, will use string matching: {e}"
            )
            focus_embedding = None

    # 安全检查：确保 focal_points 和 summary_results 长度匹配
    focal_points = state.get("plan", {}).get("focal_points", [])
    summary_results = state.get("summary_results", [])
    execution_status = state.get("execution_status", [])

    layered_single_report = (
        len(focal_points) != len(summary_results)
        and len(summary_results) == 1
        and len(execution_status) == 1
    )
    if len(focal_points) != len(summary_results) and not layered_single_report:
        raise ValueError(
            f"focal_points 数量 ({len(focal_points)}) 与 summary_results 数量 ({len(summary_results)}) 不匹配"
        )

    if layered_single_report:
        successful_items = (
            [(point, summary_results[0], True) for point in focal_points]
            if execution_status[0]
            else []
        )
        memory_items = []
        if execution_status[0]:
            plan = state.get("plan", {})
            topic = (
                plan.get("today_pattern")
                or plan.get("daily_overview")
                or "Today Brief"
            )
            reasoning = plan.get("today_pattern") or "Layered daily brief"
            memory_items = [({"topic": topic, "reasoning": reasoning}, summary_results[0])]
    else:
        # 过滤出成功的 point 和 result
        successful_items = [
            (point, result, status)
            for point, result, status in zip(
                focal_points, summary_results, execution_status
            )
            if status
        ]
        memory_items = [(point, result) for point, result, _ in successful_items]

    used_article_ids = [
        aid for point, _, _ in successful_items for aid in point["article_ids"]
    ]
    failed_count = len(focal_points) - len(successful_items)
    if failed_count > 0:
        logger.info(f"清理 {failed_count} 个失败的 point 及其相关数据")

    # 只有旧workflow才保存到exclude表
    excluded_articles = []
    group_ids = [group.id for group in state["groups"]]
    # 只排除成功的 point 涉及的 articles
    excluded_articles = [
        (article["id"], group_ids, article["pub_date"], focus, focus_embedding)
        for article in state["scored_articles"]
        if article["id"] in used_article_ids
    ]

    # 准备摘要记忆数据
    summary_memories = []
    embeddings = None

    if memory_items:
        # 尝试生成 embeddings
        if is_embedding_configured():
            try:
                # 使用 topic + reasoning + content 作为 embedding 的文本
                # 这样可以更好地捕捉完整语义
                texts_to_embed = [
                    f"{point['topic']}: {point['reasoning']}\n\n{result[:SUMMARY_EMBEDDING_MAX_LENGTH]}"
                    for point, result in memory_items
                ]
                embeddings = await embed_texts(texts_to_embed)
                logger.info(
                    "Generated %d embeddings for summary memories", len(embeddings)
                )
            except EmbeddingError as e:
                logger.warning(
                    "Failed to generate embeddings, saving without vectors: %s", e
                )
                embeddings = None
        else:
            logger.debug("Embedding service not configured, skipping vector generation")

        # 构建记忆数据
        for i, (point, result) in enumerate(memory_items):
            embedding = embeddings[i] if embeddings else None
            # 截断以匹配数据库字段长度限制 (topic: VARCHAR(256), reasoning: VARCHAR(512))
            topic = point["topic"][:256]
            reasoning = point["reasoning"][:512]
            summary_memories.append(
                (topic, reasoning, result, embedding)
            )

    async def save_to_db(cur):
        # 只有旧workflow才保存到exclude表
        if excluded_articles:
            # 根据是否有 embedding 使用不同的 SQL
            if focus_embedding is not None:
                await cur.executemany(
                    """
                    INSERT INTO excluded_feed_item_ids (item_id, group_ids, pub_date, focus, focus_embedding)
                    VALUES (%s, %s::integer[], %s, %s, %s::vector)
                    """,
                    excluded_articles,
                )
            else:
                # 没有 embedding 时，只保存字符串 focus
                articles_without_embedding = [
                    (item_id, group_ids, pub_date, focus)
                    for item_id, group_ids, pub_date, focus, _ in excluded_articles
                ]
                await cur.executemany(
                    """
                    INSERT INTO excluded_feed_item_ids (item_id, group_ids, pub_date, focus)
                    VALUES (%s, %s::integer[], %s, %s)
                    """,
                    articles_without_embedding,
                )
        if summary_memories:
            # 根据是否有 embedding 使用不同的 SQL
            if embeddings:
                await cur.executemany(
                    """
                    INSERT INTO summary_memories (topic, reasoning, content, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    """,
                    summary_memories,
                )
            else:
                # 不包含 embedding 的情况
                memories_without_embedding = [
                    (m[0], m[1], m[2]) for m in summary_memories
                ]
                await cur.executemany(
                    """
                    INSERT INTO summary_memories (topic, reasoning, content)
                    VALUES (%s, %s, %s)
                    """,
                    memories_without_embedding,
                )

    await execute_async_transaction(save_to_db)


async def search_memory(
    queries: Sequence[str],
    days_ago: int = 7,
    limit: int = 10,
    similarity_threshold: float = 0.3,
) -> dict[int, SummaryMemory]:
    """搜索历史记忆

    在历史摘要记忆库中搜索相关内容。支持两种搜索模式：
    1. 向量语义搜索（默认）：使用 embedding 进行语义相似度搜索
    2. 关键词搜索（备选）：当向量搜索不可用时，使用 ILIKE 模糊匹配

    Args:
        queries: 搜索关键词/查询文本序列
        days_ago: 搜索多少天前的记忆
        limit: 返回结果数量限制
        similarity_threshold: 向量搜索相似度阈值

    Returns:
        记忆ID到记忆对象的映射
    """
    # 过滤空查询
    valid_queries = [q for q in queries if q and q.strip()]
    if not valid_queries:
        return {}

    if days_ago <= 0:
        raise ValueError("days_ago 必须大于 0")

    if limit <= 0:
        raise ValueError("limit 必须大于 0")

    # 尝试使用向量搜索
    if is_embedding_configured():
        try:
            return await _vector_search(
                valid_queries, days_ago, limit, similarity_threshold
            )
        except EmbeddingError as e:
            logger.warning(
                "Vector search failed, falling back to keyword search: %s", e
            )
        except Exception as e:
            logger.warning("Vector search error, falling back to keyword search: %s", e)

    # 回退到关键词搜索
    return await _keyword_search(valid_queries, days_ago, limit)


async def _vector_search(
    queries: list[str],
    days_ago: int,
    limit: int,
    similarity_threshold: float,
) -> dict[int, SummaryMemory]:
    """使用向量相似度进行语义搜索"""
    # 将所有查询合并为一段文本
    combined_query = " ".join(queries)
    query_embedding = await embed_text(combined_query)

    async with get_async_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # 使用余弦相似度搜索
            # 1 - (embedding <=> query) 得到相似度分数 (0-1)
            await cur.execute(
                """
                SELECT 
                    id, topic, reasoning, content,
                    1 - (embedding <=> %s::vector) as similarity
                FROM summary_memories
                WHERE embedding IS NOT NULL
                  AND created_at >= NOW() - (%s * INTERVAL '1 day')
                  AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_embedding,
                    days_ago,
                    query_embedding,
                    similarity_threshold,
                    query_embedding,
                    limit,
                ),
            )
            rows = await cur.fetchall()

            if rows:
                logger.info(
                    "Vector search found %d memories (similarity range: %.3f - %.3f)",
                    len(rows),
                    rows[-1]["similarity"] if rows else 0,
                    rows[0]["similarity"] if rows else 0,
                )

            return {
                row["id"]: SummaryMemory(
                    id=row["id"],
                    topic=row["topic"],
                    reasoning=row["reasoning"],
                    content=row["content"],
                )
                for row in rows
            }


async def _keyword_search(
    queries: list[str],
    days_ago: int,
    limit: int,
) -> dict[int, SummaryMemory]:
    """使用关键词模糊匹配搜索（备选方案）"""
    patterns = [f"%{q}%" for q in queries]

    async with get_async_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, topic, reasoning, content
                FROM summary_memories
                WHERE topic ILIKE ANY(%s)
                  AND created_at >= NOW() - (%s * INTERVAL '1 day')
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (patterns, days_ago, limit),
            )
            rows = await cur.fetchall()
            logger.info("Keyword search found %d memories", len(rows))
            return {row["id"]: SummaryMemory(**row) for row in rows}


async def backfill_embeddings(
    batch_size: int = 50,
    max_records: int = 0,
) -> int:
    """为历史记忆补充 embedding

    为数据库中缺少 embedding 的历史记忆记录生成并补充向量嵌入。
    这是一个一次性的数据迁移操作，用于将现有数据升级到支持向量搜索。

    Args:
        batch_size: 每批处理的记录数量
        max_records: 最大处理记录数，0 表示处理所有缺少 embedding 的记录

    Returns:
        处理的记录数量
    """
    if not is_embedding_configured():
        raise RuntimeError("Embedding service not configured")

    total_processed = 0

    while True:
        # 获取一批缺少 embedding 的记录
        async with get_async_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                limit = batch_size
                if max_records > 0:
                    limit = min(batch_size, max_records - total_processed)

                if limit <= 0:
                    break

                await cur.execute(
                    """
                    SELECT id, topic, reasoning, content
                    FROM summary_memories
                    WHERE embedding IS NULL
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = await cur.fetchall()

        if not rows:
            break

        # 生成 embeddings - 包含 topic + reasoning + content
        texts = [
            f"{row['topic']}: {row['reasoning']}\n\n{row['content'][:SUMMARY_EMBEDDING_MAX_LENGTH]}"
            for row in rows
        ]
        try:
            embeddings = await embed_texts(texts)
        except EmbeddingError as e:
            logger.error("Failed to generate embeddings in backfill: %s", e)
            raise

        # 更新数据库
        updates = [(emb, row["id"]) for row, emb in zip(rows, embeddings)]

        async def update_embeddings(cur):
            await cur.executemany(
                """
                UPDATE summary_memories
                SET embedding = %s::vector
                WHERE id = %s
                """,
                updates,
            )

        await execute_async_transaction(update_embeddings)

        total_processed += len(rows)
        logger.info("Backfill progress: %d records processed", total_processed)

        if max_records > 0 and total_processed >= max_records:
            break

    logger.info("Backfill completed: %d total records processed", total_processed)
    return total_processed
