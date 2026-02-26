import logging

from core.db.pool import execute_transaction, get_connection
from apps.backend.exception import BizException
from distill_lib.core.models.feed import Feed, FeedGroup

logger = logging.getLogger(__name__)


def create_group(title: str, desc: str, feed_ids: list[int]):
    def insert_group(cur):
        sql = """
              INSERT INTO feed_groups (title, "desc")
              VALUES (%s, %s)
              ON CONFLICT (title) DO NOTHING
              RETURNING id \
              """
        cur.execute(sql, (title, desc))
        res = cur.fetchone()
        if not res:
            return
        gid = res[0]
        _add_feeds_to_group(cur, gid, feed_ids)
        return gid

    return execute_transaction(insert_group)


def join_group(group_id: int, feed_ids: list[str]):
    execute_transaction(_add_feeds_to_group, group_id, feed_ids)

def get_groups(group_ids: list[int]):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, "desc" FROM feed_groups WHERE id = ANY(%s)""",
                (group_ids,),
            )
            return {
                row[0]: FeedGroup(id=row[0], title=row[1], desc=row[2])
                for row in cur.fetchall()
            }

def get_group_detail(group_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, "desc" FROM feed_groups WHERE id = %s""",
                (group_id,),
            )
            res = cur.fetchone()
            if not res:
                raise BizException(f"Group {group_id} not found")
            group = FeedGroup(id=res[0], title=res[1], desc=res[2])
            cur.execute(
                """SELECT id, title, url, last_updated, description, status FROM feeds WHERE id IN (SELECT feed_id FROM feed_group_items WHERE feed_group_id = %s)""",
                (group_id,),
            )
            group.feeds = [
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
            return group


def update_group(group_id: int, title: str, desc: str, feed_ids: list[int]):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, "desc" FROM feed_groups WHERE id = %s""",
                (group_id,),
            )
            res = cur.fetchone()
            if not res:
                raise BizException(f"Group {group_id} not found")
            cur.execute(
                """SELECT feed_id FROM feed_group_items WHERE feed_group_id = %s""",
                (group_id,),
            )
            existing_feed_ids = [row[0] for row in cur.fetchall()]
            new_feed_ids = [
                feed_id for feed_id in feed_ids if feed_id not in existing_feed_ids
            ]
            removed_feed_ids = [
                feed_id for feed_id in existing_feed_ids if feed_id not in feed_ids
            ]
            logger.info(
                f"Removed feed ids: {removed_feed_ids}, new feed ids: {new_feed_ids}"
            )
            if removed_feed_ids:
                cur.execute(
                    """DELETE FROM feed_group_items WHERE feed_id = ANY(%s) AND feed_group_id = %s""",
                    (removed_feed_ids, group_id),
                )
            if new_feed_ids:
                logger.info(f"Adding new feed ids: {new_feed_ids}")
                _add_feeds_to_group(cur, group_id, new_feed_ids)
            cur.execute(
                """UPDATE feed_groups SET title = %s, "desc" = %s WHERE id = %s""",
                (title, desc, group_id),
            )


def _add_feeds_to_group(cur, group_id, feed_ids):
    sql = """
          INSERT INTO feed_group_items (feed_id, feed_group_id)
          VALUES (%s, %s)
          ON CONFLICT DO NOTHING \
          """
    data_to_insert = [(feed_id, group_id) for feed_id in feed_ids]
    cur.executemany(sql, data_to_insert)


def delete_group(group_id: int):
    def _delete(cur):
        cur.execute(
            "DELETE FROM feed_group_items WHERE feed_group_id = %s",
            (group_id,),
        )
        cur.execute(
            "DELETE FROM feed_groups WHERE id = %s",
            (group_id,),
        )
        cur.execute(
            """
            UPDATE schedules 
            SET group_ids = array_remove(group_ids, %s::int)
            WHERE group_ids @> ARRAY[%s::int]
            """,
            (group_id, group_id)
        )

    execute_transaction(_delete)


def get_all_groups_with_feeds() -> list[FeedGroup]:
    """
    Get all feed groups with their associated feeds.
    Returns:
        List of FeedGroup objects, each containing its feeds.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all groups
            cur.execute("""SELECT id, title, "desc" FROM feed_groups ORDER BY id ASC""")
            groups = {
                row[0]: FeedGroup(id=row[0], title=row[1], desc=row[2])
                for row in cur.fetchall()
            }

            if not groups:
                return []

            # Get all feeds with their group associations
            cur.execute(
                """
                SELECT f.id, f.title, f.url, f.last_updated, f.description, f.status, fgi.feed_group_id
                FROM feeds f
                JOIN feed_group_items fgi ON f.id = fgi.feed_id
                WHERE fgi.feed_group_id = ANY(%s)
                ORDER BY f.id ASC
                """,
                (list(groups.keys()),),
            )

            for row in cur.fetchall():
                feed = Feed(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    last_updated=row[3],
                    desc=row[4],
                    status=row[5],
                )
                group_id = row[6]
                if group_id in groups:
                    groups[group_id].feeds.append(feed)

            return list(groups.values())


def get_group_with_feeds(group_ids: list[int]) -> list[FeedGroup]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, "desc" FROM feed_groups WHERE id = ANY(%s)""",
                (group_ids,),
            )
            groups = {
                row[0]: FeedGroup(id=row[0], title=row[1], desc=row[2])
                for row in cur.fetchall()
            }
            cur.execute(
                """
                SELECT f.id, f.title, f.url, f.last_updated, f.description, f.status, fgi.feed_group_id 
                FROM feeds f
                JOIN feed_group_items fgi ON f.id = fgi.feed_id
                WHERE fgi.feed_group_id = ANY(%s)
                ORDER BY f.id ASC
                """,
                (group_ids,),
            )
            for row in cur.fetchall():
                feed = Feed(
                    id=row[0],
                    title=row[1],
                    url=row[2],
                    last_updated=row[3],
                    desc=row[4],
                    status=row[5],
                )
                group_id = row[6]
                if group_id in groups:
                    groups[group_id].feeds.append(feed)
            return list(groups.values())

