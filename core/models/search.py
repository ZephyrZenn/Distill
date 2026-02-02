from typing import TypedDict, NotRequired

class SearchResult(TypedDict):
    title: str
    url: str
    content: str
    score: float
    raw_content: NotRequired[str]  # Tavily 返回的原始网页内容（需开启 include_raw_content）