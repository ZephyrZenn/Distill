from datetime import datetime
from typing import Literal, Optional

from core.constants import DEFAULT_FEED_LAST_USED_DATE


class Feed:
    def __init__(
        self,
        id: int,
        title: str,
        url: str,
        last_updated: datetime = DEFAULT_FEED_LAST_USED_DATE,
        desc: str = "",
        status: Literal['active', 'unreachable'] = 'active',
    ):
        self.id = id
        self.title = title
        self.url = url
        self.last_updated = last_updated
        self.desc = desc
        self.status = status
        self.articles = []

    def to_dict(self) -> dict:
        """Serialize feed to a JSON-friendly dict."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "last_updated": self.last_updated,
            "description": self.desc,
            "status": self.status,
        }


class FeedArticle:
    def __init__(
        self,
        id: str,
        title: str,
        url: str,
        content: Optional[str],
        pub_date: datetime,
        summary: str,
        has_full_content: bool,
    ):
        self.id = id
        self.title = title
        self.url = url
        self.content = content
        self.summary = summary
        self.pub_date = pub_date
        self.has_full_content = has_full_content

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "summary": self.summary,
            "pub_date": self.pub_date.isoformat() if self.pub_date else None,
            "has_full_content": self.has_full_content,
        }


class FeedGroup:
    def __init__(self, id: int, title: str, desc: str, feeds: list[Feed] | None = None):
        self.id = id
        self.title = title
        self.desc = desc
        self.feeds = feeds if feeds is not None else []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "desc": self.desc,
            "feeds": [f.to_dict() for f in self.feeds] if self.feeds else [],
        }


class FeedBrief:
    def __init__(
        self,
        id: int,
        content: str,
        pub_date: datetime,
        group_ids: list[int] = None,
        summary: str = "",
        overview: str = "",
        ext_info: list[dict] = None,
        expandable_topics: list[dict] = None,
    ):
        self.id = id
        self.content = content
        self.pub_date = pub_date
        self.group_ids = group_ids if group_ids is not None else []
        self.summary = summary
        self.overview = overview
        self.ext_info = ext_info if ext_info is not None else []
        self.expandable_topics = (
            expandable_topics if expandable_topics is not None else []
        )

    def to_view_model(self, groups_dict: dict[int, FeedGroup], include_content: bool = True) -> dict:
        """转换为视图模型

        Args:
            groups_dict: 分组ID到分组对象的映射
            include_content: 是否包含完整内容（content 和 ext_info），默认 True
        """
        groups = [groups_dict[gid] for gid in self.group_ids if gid in groups_dict]
        result = {
            "id": self.id,
            "pub_date": self.pub_date,
            "groups": groups,
            "summary": self.summary,
            "overview": self.overview,
        }
        if include_content:
            result["content"] = self.content
            result["ext_info"] = self.ext_info
            result["expandable_topics"] = self.expandable_topics
        return result
