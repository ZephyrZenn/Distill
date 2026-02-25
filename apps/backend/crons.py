import logging
from core.db.pool import get_async_connection

logger = logging.getLogger(__name__)

# 默认最小文章数阈值：24小时内至少有20篇文章才跳过爬虫
DEFAULT_MIN_ARTICLE_COUNT = 20


async def _check_available_articles(group_ids: list[int], hour_gap: int = 24) -> int:
    """检查指定分组在指定时间内的可用文章数量

    Args:
        group_ids: 分组ID列表
        hour_gap: 检查过去几小时的文章，默认24小时

    Returns:
        可用文章数量
    """
    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            sql = """
                SELECT COUNT(DISTINCT fi.id)
                FROM feed_items fi
                JOIN feed_group_items fgi ON fi.feed_id = fgi.feed_id
                WHERE fgi.feed_group_id = ANY(%s)
                    AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
            """
            await cur.execute(sql, (group_ids, hour_gap))
            row = await cur.fetchone()
            return row[0] if row else 0


async def generate_scheduled_brief(
    schedule_id: str,
    group_ids: list[int],
    focus: str,
    min_article_count: int = DEFAULT_MIN_ARTICLE_COUNT,
):
    """Generate a brief for specific groups with custom focus (async, single event loop).

    先检查库存文章数量，如果充足（>= min_article_count）则直接生成简报。
    如果不足，则先爬取新文章再生成简报。
    爬虫失败不会影响简报生成，只要有库存文章就可以生成。

    Args:
        schedule_id: 调度任务ID
        group_ids: 分组ID列表
        focus: 用户关注点
        min_article_count: 最小文章数阈值，默认20篇
    """
    from apps.backend.services.brief_service import generate_brief_for_groups_async
    from apps.backend.services.feed_service import retrieve_new_feeds

    logger.info(
        "Generating scheduled brief %s for groups %s with focus: %s",
        schedule_id,
        group_ids,
        focus,
    )
    try:
        # 1. 检查库存文章数量
        available_count = await _check_available_articles(group_ids, hour_gap=24)
        logger.info(
            "Schedule %s: found %d articles in database for groups %s",
            schedule_id,
            available_count,
            group_ids,
        )

        # 2. 判断是否需要爬取
        if available_count >= min_article_count:
            logger.info(
                "Schedule %s: sufficient articles (%d >= %d), skipping crawl",
                schedule_id,
                available_count,
                min_article_count,
            )
        else:
            logger.info(
                "Schedule %s: insufficient articles (%d < %d), starting crawl",
                schedule_id,
                available_count,
                min_article_count,
            )
            try:
                await retrieve_new_feeds(group_ids=group_ids)
                logger.info("Schedule %s: crawl completed", schedule_id)
            except Exception as e:
                # 爬虫失败不影响简报生成，只要有库存文章就可以
                logger.warning(
                    "Schedule %s: crawl failed but continuing with brief generation: %s",
                    schedule_id,
                    e,
                )
                # 重新检查文章数
                new_count = await _check_available_articles(group_ids, hour_gap=24)
                if new_count == 0:
                    logger.error(
                        "Schedule %s: no articles available after crawl failure, aborting",
                        schedule_id,
                    )
                    return

        # 3. 生成简报
        await generate_brief_for_groups_async(
            task_id=schedule_id,
            group_ids=group_ids,
            focus=focus,
        )
        logger.info("Finished generating scheduled brief %s", schedule_id)
    except Exception as e:
        logger.exception("Error generating scheduled brief %s: %s", schedule_id, e)


def check_feed_health():
    """
    Check the health of the feed.
    """
    from apps.backend.services.feed_service import (
        check_feed_health as _check_feed_health,
    )

    _check_feed_health()
