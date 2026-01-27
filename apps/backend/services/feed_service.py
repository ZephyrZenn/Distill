import asyncio
import datetime
import logging
from typing import Optional

from core.constants import SUMMARY_LENGTH
from core.crawler import fetch_all_contents
from core.db.pool import get_async_connection, execute_transaction, get_connection
from core.models.feed import Feed
from core.parsers import parse_feed, parse_opml

from apps.backend.exception import BizException

logger = logging.getLogger(__name__)


def import_opml_config(file_url: Optional[str] = None, content: Optional[str] = None):
    if file_url:
        with open(file_url, "r") as f:
            file_text = f.read()
            feeds = parse_opml(file_text)
    elif content:
        feeds = parse_opml(content)
    else:
        raise BizException("No file URL or content provided")

    execute_transaction(_insert_feeds, feeds)


async def retrieve_new_feeds(group_ids: list[int] = None):
    """
    Retrieves new feeds from websites and update the databases.
    Args:
      group_ids: The feed group that needs to be updated. If None, all groups will be updated.

    """
    feeds = []
    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            if not group_ids:
                await cur.execute(
                    """
                            SELECT id, title, url, last_updated, description, status
                            from feeds
                            """
                )
                rows = await cur.fetchall()
            else:
                await cur.execute(
                    """
                            SELECT id, title, url, last_updated, description, status
                            from feeds
                            where id in (SELECT feed_id
                                         FROM feed_group_items
                                         WHERE feed_group_id = ANY(%s))
                            """,
                    (group_ids,),
                )
                rows = await cur.fetchall()
            feeds = [Feed(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows]
    if not feeds:
        return
    # feedparser 是阻塞操作，放到线程池避免阻塞事件循环
    loop = asyncio.get_running_loop()
    articles = await loop.run_in_executor(None, parse_feed, feeds)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    filtered_articles = {}
    for feed_title, feed_articles in articles.items():
        recent_articles = [a for a in feed_articles if a.pub_date >= cutoff]
        if recent_articles:
            filtered_articles[feed_title] = recent_articles
    articles = filtered_articles
    if articles:
        candidate_ids = {
            a.id for feed_articles in articles.values() for a in feed_articles if a.id
        }
        if candidate_ids:
            async with get_async_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """SELECT id FROM feed_items WHERE id = ANY(%s)""",
                        (list(candidate_ids),),
                    )
                    existing_ids = {row[0] for row in await cur.fetchall()}
            if existing_ids:
                deduped_articles = {}
                for feed_title, feed_articles in articles.items():
                    unique_articles = [
                        a for a in feed_articles if a.id not in existing_ids
                    ]
                    if unique_articles:
                        deduped_articles[feed_title] = unique_articles
                articles = deduped_articles
    urls = {
        a.url: a for arts in articles.values() for a in arts if not a.has_full_content
    }
    contents = await fetch_all_contents(list(urls.keys()))
    for url, content in contents.items():
        if not content:
            continue
        article = urls[url]
        article.content = content
        if not article.summary:
            article.summary = content[:SUMMARY_LENGTH]

    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            for feed in feeds:
                if feed.title not in articles:
                    continue
                feed_articles = articles[feed.title]
                logger.info(
                    "Retrieving %d articles for feed %s", len(feed_articles), feed.title
                )
                item_sql = """
                           INSERT INTO feed_items (id, feed_id, title, link, pub_date, summary)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (id) DO NOTHING \
                           """
                item_content_sql = """
                                   INSERT INTO feed_item_contents (feed_item_id, content)
                                   VALUES (%s, %s)
                                   ON CONFLICT (feed_item_id) DO NOTHING \
                                   """
                await cur.executemany(
                    item_sql,
                    [
                        (a.id, feed.id, a.title, a.url, a.pub_date, a.summary)
                        for a in feed_articles
                    ],
                )
                await cur.executemany(
                    item_content_sql, [(a.id, a.content) for a in feed_articles]
                )
            update_feed_sql = """
                              UPDATE feeds
                              SET last_updated = %s
                              WHERE id = %s \
                              """
            await cur.executemany(
                update_feed_sql, [(datetime.datetime.now(), feed.id) for feed in feeds]
            )
            await conn.commit()


def retrieve_new_feeds_sync(group_ids: list[int] = None):
    """同步包装：仅供脚本/测试使用，避免在运行事件循环内调用。"""
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "retrieve_new_feeds_sync cannot be called when an event loop is running; use await retrieve_new_feeds instead"
        )
    except RuntimeError:
        # no running loop
        return asyncio.run(retrieve_new_feeds(group_ids))


def get_all_feeds():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, url, last_updated, description, status FROM feeds ORDER BY id"""
            )
            return [
                Feed(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    last_updated=row[3],
                    desc=row[4],
                    status=row[5],
                )
                for row in cur.fetchall()
            ]


def add_feed(title: str, description: str, url: str):
    execute_transaction(
        _insert_feeds, [Feed(id=0, title=title, url=url, desc=description)]
    )


def update_feed(id: int, title: str, description: str, url: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE feeds SET title = %s, url = %s, description = %s WHERE id = %s""",
                (title, url, description, id),
            )


def delete_feed(id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""DELETE FROM feeds WHERE id = %s""", (id,))
            cur.execute("""DELETE FROM feed_group_items WHERE feed_id = %s""", (id,))


def _insert_feeds(cur, feeds):
    if not feeds:
        return
    insert_sql = """
                  INSERT INTO feeds (title, url, status, description, last_updated)
                  VALUES (%s, %s, %s, %s, %s)
                  ON CONFLICT(url) DO NOTHING
                  RETURNING id \
                  """
    data_to_insert = [
        (
            feed.title,
            feed.url,
            feed.status,
            feed.desc,
            feed.last_updated,
        )
        for feed in feeds
    ]
    cur.executemany(insert_sql, data_to_insert)


def get_feed_items(hour_gap: int, group_ids: Optional[list[int]]) -> list[dict]:
    """
    Get all feed_items from the last `hour_gap` hours, optionally filtering by feed group IDs.
    Args:
        hour_gap (int): Number of previous hours to look back.
        group_ids (Optional[list[int]]): If provided, only get items from feeds in these group_ids.
    Returns:
        List of feed_items as dicts.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            if group_ids is not None and len(group_ids) > 0:
                sql = """
                    SELECT DISTINCT fi.id, fi.feed_id, fi.title, fi.link, fi.summary, fi.pub_date
                    FROM feed_items fi
                    JOIN feed_group_items fgi ON fi.feed_id = fgi.feed_id
                    WHERE fgi.feed_group_id = ANY(%s)
                        AND fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                    ORDER BY fi.pub_date DESC
                """
                cur.execute(sql, (group_ids, hour_gap))
            else:
                sql = """
                    SELECT fi.id, fi.feed_id, fi.title, fi.link, fi.summary, fi.pub_date
                    FROM feed_items fi
                    WHERE fi.pub_date >= NOW() - INTERVAL '1 hour' * %s
                    ORDER BY fi.pub_date DESC
                """
                cur.execute(sql, (hour_gap,))
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "feed_id": row[1],
                    "title": row[2],
                    "link": row[3],
                    "summary": row[4],
                    "pub_date": row[5],
                }
                for row in rows
            ]


def check_feed_health():
    """
    Check the health of the feed.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, url, status FROM feeds""")
            feeds = [
                {"id": row[0], "url": row[1], "status": row[2]}
                for row in cur.fetchall()
            ]
    import requests

    update_feeds = []
    for feed in feeds:
        try:
            response = requests.get(feed["url"], timeout=5)
            if response.status_code != 200:
                logger.warning(
                    f"Feed {feed['id']} url {feed['url']} returned status {response.status_code}"
                )
                new_status = "unreachable"
            else:
                new_status = "active"
        except Exception as e:
            logger.warning(
                f"Feed {feed['id']} url {feed['url']} request exception: {e}"
            )
            new_status = "unreachable"
        if new_status != feed["status"]:
            update_feeds.append((new_status, feed["id"]))
    if update_feeds:
        update_sql = """
                      UPDATE feeds SET status = %s WHERE id = %s
                      """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(update_sql, update_feeds)
