"""搜索工具函数模块

提供网页搜索和内容抓取相关的工具函数。
"""

import logging
from typing import Literal

from core.crawler import fetch_all_contents
from core.crawler.search_engine import get_search_client, search
from core.models.search import SearchResult

logger = logging.getLogger(__name__)


async def fetch_web_contents(urls: list[str]) -> dict[str, str]:
    """批量获取网页内容

    批量抓取指定 URL 列表的网页正文内容。使用异步并发请求提高效率，
    自动处理各种网页格式，提取主要文本内容并清理 HTML 标签。

    Args:
        urls: 需要抓取内容的 URL 列表

    Returns:
        字典，键为 URL，值为抓取到的网页正文内容。
        如果某个 URL 抓取失败，该 URL 对应的值为空字符串。
    """
    if not urls:
        return {}

    return await fetch_all_contents(urls)


async def search_web(
    query: str,
    time_range: Literal["day", "week", "month", "year"] = "week",
    max_results: int = 5,
    include_raw_content: bool = False,
    topic: Literal["general", "news", "finance"] = "general",
) -> list[SearchResult]:
    """搜索网页

    使用搜索引擎搜索互联网内容，
    调用搜索引擎 API 获取搜索结果

    Args:
        query: 搜索查询语句
        time_range: 搜索结果的时间范围限制 ('day', 'week', 'month', 'year')
        max_results: 期望返回的最大结果数量
        include_raw_content: 是否获取原始网页内容（Tavily 特性）
        topic: 搜索类别 ('general', 'news', 'finance')

    Returns:
        搜索结果列表，每个结果包含 title、url、content（摘要）、score，
        如果启用 include_raw_content 还可能包含 raw_content（原始网页内容）
    """
    if not query or not query.strip():
        raise ValueError("搜索查询不能为空")

    if max_results <= 0:
        raise ValueError("max_results 必须大于 0")

    # 检查搜索引擎是否可用
    if not get_search_client():
        raise RuntimeError("搜索引擎未配置或不可用，请先检查配置")

    search_results = search(
        query,
        time_range=time_range,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

    if not search_results:
        return []

    return search_results


def is_search_engine_available() -> bool:
    """检查搜索引擎是否可用"""
    return get_search_client() is not None