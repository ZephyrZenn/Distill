"""过滤/关键词提取工具函数模块

提供使用 LLM 进行关键词提取的工具函数。
"""

from agent.models import RawArticle
from core.llm_client import LLMClient


async def find_keywords_with_llm(
    client: LLMClient, articles: list[RawArticle]
) -> list[str]:
    """使用 LLM 提取关键词

    使用大语言模型（LLM）从一批文章中智能提取核心关键词。
    关键词类型包括：公司名称、产品名称、技术术语、人物名称等实体词。
    该函数通过分析文章标题和摘要，识别出最具代表性的 5-8 个关键词。

    Args:
        client: AI 生成器客户端
        articles: 待分析的文章列表

    Returns:
        包含 5-8 个提取出的核心关键词的列表，已去重和清理
    """
    if not articles:
        return []

    combined_text = "\n".join(
        [f"{article['title']} | {article['summary']}" for article in articles]
    )

    if not combined_text.strip():
        return []

    prompt = f"""
    请从以下资讯摘要中提取 5-8 个最核心的实体词（公司、产品、技术、人物）或关键词。
    仅输出关键词，用逗号隔开，不要有任何解释。
    内容如下：
    {combined_text}
    """

    response = await client.completion(prompt)

    if not response:
        return []

    keywords = [k.strip() for k in response.replace("，", ",").split(",") if k.strip()]
    return keywords
