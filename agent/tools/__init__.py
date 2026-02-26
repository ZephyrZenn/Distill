"""Agent 工具模块

提供统一的工具函数。

使用示例：
    # 使用函数（推荐）
    from agent.tools import get_recent_group_update, search_memory, search_web
    
    groups, articles = await get_recent_group_update(24, [1, 2], focus="AI")
    memories = await search_memory(["关键词"], days_ago=7)
    results = await search_web("查询", time_range="week")
"""

# 数据库工具函数
from agent.tools.db_tool import (
    get_recent_group_update,
    get_all_feeds,
    get_recent_feed_update,
    get_article_content,
)

# 记忆工具函数
from agent.tools.memory_tool import (
    save_current_execution_records,
    search_memory,
    backfill_embeddings,
)

# 搜索工具函数
from distill_lib.agent.tools.search_tool import (
    fetch_web_contents,
    search_web,
    is_search_engine_available,
)

# 过滤/关键词提取函数
from distill_lib.agent.tools.filter_tool import find_keywords_with_llm

# 写作工具函数
from distill_lib.agent.tools.writing_tool import write_article, review_article


__all__ = [
    # 数据库函数
    "get_recent_group_update",
    "get_all_feeds",
    "get_recent_feed_update",
    "get_article_content",
    # 记忆函数
    "save_current_execution_records",
    "search_memory",
    "backfill_embeddings",
    # 搜索函数
    "fetch_web_contents",
    "search_web",
    "is_search_engine_available",
    # 过滤函数
    "find_keywords_with_llm",
    # 写作函数
    "write_article",
    "review_article",
]
