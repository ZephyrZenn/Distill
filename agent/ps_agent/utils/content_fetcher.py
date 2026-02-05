from agent.ps_agent.state import ResearchItem
from agent.tools import fetch_web_contents
from core.db.pool import get_async_connection


async def fetch_contents(
    items: list[ResearchItem],
) -> tuple[dict[str, str], dict[str, str]]:
    urls = [item.get("url", "") for item in items if item.get("source") == "web"]
    web_contents = await fetch_web_contents(urls)
    ids = [item.get("id", "") for item in items if item.get("source") == "feed"]
    async with get_async_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT feed_item_id, content FROM feed_item_contents WHERE feed_item_id = ANY(%s)",
                (ids,),
            )
            rows = await cur.fetchall()
            feed_contents = {row[0]: row[1] for row in rows}
    return web_contents, feed_contents
