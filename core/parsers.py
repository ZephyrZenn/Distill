"""Compatibility wrapper for feed parsing.

Canonical implementation now lives in distill_lib.parsers.
"""

from __future__ import annotations

from distill_lib.feed_models import Feed as LibFeed
from distill_lib.parsers import parse_feed as lib_parse_feed
from distill_lib.parsers import parse_html_content  # noqa: F401
from distill_lib.parsers import parse_opml as lib_parse_opml

from core.models.feed import Feed, FeedArticle


def parse_opml(file_text: str) -> list[Feed]:
    return [Feed(f.id, f.title, f.url) for f in lib_parse_opml(file_text)]


def parse_feed(feeds: list[Feed]) -> dict[str, list[FeedArticle]]:
    lib_feeds = [LibFeed(id=feed.id, title=feed.title, url=feed.url) for feed in feeds]
    lib_articles = lib_parse_feed(lib_feeds)

    return {
        title: [
            FeedArticle(
                id=article.id,
                title=article.title,
                url=article.url,
                content=article.content,
                pub_date=article.pub_date,
                summary=article.summary,
                has_full_content=article.has_full_content,
            )
            for article in articles
        ]
        for title, articles in lib_articles.items()
    }


__all__ = ["parse_opml", "parse_feed", "parse_html_content"]
