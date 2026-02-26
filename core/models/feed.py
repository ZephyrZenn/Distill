"""Compatibility shim for feed models.

Canonical definitions live in distill_lib.core.models.feed.
"""

from distill_lib.core.models.feed import Feed, FeedArticle, FeedBrief, FeedGroup

__all__ = ["Feed", "FeedArticle", "FeedBrief", "FeedGroup"]
