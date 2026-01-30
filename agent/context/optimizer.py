"""Content optimizer for truncating and prioritizing content.

Provides intelligent content truncation, summarization, and prioritization.
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

from agent.models import RawArticle, SummaryMemory
from core.llm_client import LLMClient
from core.embedding import (
    embed_text,
    embed_texts,
    is_embedding_configured,
    EmbeddingError,
)

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Cosine similarity score (0-1)
    """
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have the same length")
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


class ContentOptimizer:
    """Optimizes content for context window efficiency.
    
    Provides content truncation, summarization, and prioritization.
    """

    def __init__(
        self,
        article_max_length: int = 500,
        summary_max_length: int = 200,
        memory_max_length: int = 300,
        client: Optional[LLMClient] = None,
    ):
        """Initialize the content optimizer.
        
        Args:
            article_max_length: Maximum length for article content (characters)
            summary_max_length: Maximum length for article summaries (characters)
            memory_max_length: Maximum length for history memories (characters)
            client: Optional AIGenerator client for LLM-based keyword extraction
        """
        self.article_max_length = article_max_length
        self.summary_max_length = summary_max_length
        self.memory_max_length = memory_max_length
        self.client = client

    def truncate_text(self, text: str, max_length: int, suffix: str = "...") -> str:
        """Truncate text to a maximum length, preserving word boundaries when possible.
        
        Args:
            text: Text to truncate
            max_length: Maximum length in characters
            suffix: Suffix to append if truncated
            
        Returns:
            Truncated text
        """
        if not text or len(text) <= max_length:
            return text
        
        # Try to truncate at sentence boundary first
        truncated = text[:max_length - len(suffix)]
        
        # Find last sentence boundary
        last_period = truncated.rfind('.')
        last_exclamation = truncated.rfind('!')
        last_question = truncated.rfind('?')
        last_newline = truncated.rfind('\n')
        
        # Use the latest boundary found
        boundary = max(last_period, last_exclamation, last_question, last_newline)
        
        if boundary > max_length * 0.5:  # Only use boundary if it's not too early
            truncated = truncated[:boundary + 1]
        else:
            # Fall back to word boundary
            last_space = truncated.rfind(' ')
            if last_space > max_length * 0.5:
                truncated = truncated[:last_space]
        
        return truncated + suffix

    def truncate_article(
        self, article: RawArticle, max_content_length: int | None = None
    ) -> RawArticle:
        """Truncate an article to fit within context limits.
        
        自动检测文章是否包含完整内容，如果有则进行压缩。
        
        Args:
            article: Article to truncate
            max_content_length: Maximum length for content (None = use default)
            
        Returns:
            Truncated article
        """
        truncated = article.copy()
        
        # Truncate summary (always)
        if "summary" in truncated and truncated["summary"]:
            truncated["summary"] = self.truncate_text(
                truncated["summary"], self.summary_max_length
            )
        
        # 自动检测是否有完整内容
        has_content = "content" in truncated and truncated.get("content")
        
        if has_content:
            # 有完整内容，根据 max_content_length 决定是否压缩
            content_length = max_content_length or self.article_max_length
            truncated["content"] = self.truncate_text(
                truncated["content"], content_length
            )
        # 如果没有 content，保持原样（不添加 content 字段）
        
        return truncated

    def truncate_articles(
        self,
        articles: list[RawArticle],
        max_tokens: int | None = None,
        max_content_length: int | None = None,
    ) -> list[RawArticle]:
        """Truncate a list of articles to fit within token limits.
        
        自动检测每篇文章是否包含完整内容，根据实际情况进行压缩。
        
        Args:
            articles: List of articles to truncate
            max_tokens: Maximum tokens allowed (None for no limit)
            max_content_length: Maximum length for article content (None = use default)
            
        Returns:
            List of truncated articles
        """
        if not articles:
            return []
        
        # 自动检测哪些文章有完整内容
        articles_with_content = sum(1 for a in articles if a.get("content"))
        articles_without_content = len(articles) - articles_with_content
        
        logger.debug(
            "Truncating %d articles (%d with content, %d without)",
            len(articles),
            articles_with_content,
            articles_without_content,
        )
        
        truncated = [
            self.truncate_article(article, max_content_length) for article in articles
        ]
        
        # If max_tokens is specified, further limit the number of articles
        if max_tokens is not None:
            # 估算每篇文章的 token 数（根据是否有内容）
            # 有内容的文章估算更多 token
            estimated_per_article_with_content = 500
            estimated_per_article_without_content = 100
            
            # 计算当前总 token 数
            total_estimated = (
                articles_with_content * estimated_per_article_with_content
                + articles_without_content * estimated_per_article_without_content
            )
            
            if total_estimated > max_tokens:
                # 需要减少文章数量
                # 优先保留有内容的文章（因为它们更有价值）
                articles_with_content_list = [
                    a for a in truncated if a.get("content")
                ]
                articles_without_content_list = [
                    a for a in truncated if not a.get("content")
                ]
                
                # 计算可以保留多少文章
                remaining_tokens = max_tokens
                kept_with_content = []
                kept_without_content = []
                
                # 先保留有内容的文章
                for article in articles_with_content_list:
                    if remaining_tokens >= estimated_per_article_with_content:
                        kept_with_content.append(article)
                        remaining_tokens -= estimated_per_article_with_content
                    else:
                        break
                
                # 再保留没有内容的文章
                for article in articles_without_content_list:
                    if remaining_tokens >= estimated_per_article_without_content:
                        kept_without_content.append(article)
                        remaining_tokens -= estimated_per_article_without_content
                    else:
                        break
                
                truncated = kept_with_content + kept_without_content
                
                logger.debug(
                    "Limited articles from %d to %d based on token limit %d "
                    "(kept %d with content, %d without)",
                    len(articles),
                    len(truncated),
                    max_tokens,
                    len(kept_with_content),
                    len(kept_without_content),
                )
        
        return truncated

    def truncate_memory(self, memory: SummaryMemory) -> SummaryMemory:
        """Truncate a history memory to fit within context limits.
        
        Args:
            memory: Memory to truncate
            
        Returns:
            Truncated memory
        """
        truncated = memory.copy()
        
        if "content" in truncated and truncated["content"]:
            truncated["content"] = self.truncate_text(
                truncated["content"], self.memory_max_length
            )
        
        return truncated

    def truncate_memories(
        self, memories: list[SummaryMemory], max_count: int | None = None
    ) -> list[SummaryMemory]:
        """Truncate a list of memories.
        
        Args:
            memories: List of memories to truncate
            max_count: Maximum number of memories to keep
            
        Returns:
            List of truncated memories
        """
        if not memories:
            return []
        
        truncated = [self.truncate_memory(memory) for memory in memories]
        
        if max_count is not None and len(truncated) > max_count:
            logger.debug(
                "Limiting memories from %d to %d",
                len(truncated),
                max_count,
            )
            truncated = truncated[:max_count]
        
        return truncated

    async def prioritize_articles(
        self, articles: list[RawArticle], focus: str = ""
    ) -> list[RawArticle]:
        """Prioritize articles based on relevance to focus.
        
        Uses multiple strategies in order of preference:
        1. Vector similarity (if embedding is configured)
        2. LLM-extracted keywords (if client is available)
        3. Improved keyword matching (fallback)
        
        Args:
            articles: List of articles to prioritize
            focus: User focus string for relevance scoring
            
        Returns:
            Prioritized list of articles
        """
        if not focus or not articles:
            return articles

        # Strategy 1: Use vector similarity if embedding is configured
        if is_embedding_configured():
            try:
                return await self._prioritize_with_embedding(articles, focus)
            except Exception as e:
                logger.warning(
                    "Embedding-based prioritization failed: %s, falling back to keyword matching",
                    e,
                )

        # Strategy 2: Use LLM to extract keywords if client is available
        if self.client:
            try:
                return await self._prioritize_with_llm_keywords(articles, focus)
            except Exception as e:
                logger.warning(
                    "LLM keyword extraction failed: %s, falling back to keyword matching",
                    e,
                )

        # Strategy 3: Fallback to improved keyword matching
        return self._prioritize_with_keywords(articles, focus)

    async def _prioritize_with_embedding(
        self, articles: list[RawArticle], focus: str
    ) -> list[RawArticle]:
        """Prioritize articles using vector similarity.
        
        Args:
            articles: List of articles to prioritize
            focus: User focus string
            
        Returns:
            Prioritized list of articles
        """
        try:
            # Generate embedding for focus
            focus_embedding = await embed_text(focus)

            # Prepare article texts (title + summary, limited length)
            article_texts: list[str] = []
            has_non_empty = False
            for article in articles:
                title = article.get("title", "") or ""
                summary = article.get("summary", "") or ""
                article_text = f"{title} {summary}".strip()
                if article_text:
                    has_non_empty = True
                    article_texts.append(article_text[:500])
                else:
                    # 保留空字符串，占位，后面按 0 相似度处理
                    article_texts.append("")

            # 如果所有文章都没有可用文本，直接按原顺序返回
            if not has_non_empty:
                logger.debug(
                    "All articles are empty for embedding prioritization, returning original order"
                )
                return articles

            # 批量生成 embeddings（与 articles 一一对应）
            article_embeddings = await embed_texts(article_texts)

            # Score each article
            scored_articles = []
            for article, text, article_embedding in zip(
                articles, article_texts, article_embeddings
            ):
                if not text:
                    # 没有文本，直接给 0 分
                    scored_articles.append((article, 0.0))
                    continue

                # 计算与 focus 的相似度
                similarity = cosine_similarity(focus_embedding, article_embedding)
                scored_articles.append((article, similarity))

            # Sort by similarity (descending)
            scored_articles.sort(key=lambda x: x[1], reverse=True)
            prioritized = [article for article, _ in scored_articles]

            logger.debug(
                "Prioritized %d articles using vector similarity (focus: %s)",
                len(prioritized),
                focus[:50],
            )

            return prioritized

        except EmbeddingError as e:
            logger.warning("Embedding error: %s", e)
            raise
        except Exception as e:
            logger.error("Unexpected error in embedding prioritization: %s", e)
            raise

    async def _prioritize_with_llm_keywords(
        self, articles: list[RawArticle], focus: str
    ) -> list[RawArticle]:
        """Prioritize articles using LLM-extracted keywords.
        
        Args:
            articles: List of articles to prioritize
            focus: User focus string
            
        Returns:
            Prioritized list of articles
        """
        try:
            # Use LLM to extract keywords and synonyms from focus
            prompt = f"""请从以下用户关注点中提取5-10个核心关键词（包括同义词、相关词）。
关注点：{focus}

输出格式：仅输出关键词，用逗号分隔，不要有任何解释。
例如：人工智能,AI,机器学习,深度学习,神经网络
"""
            response = await self.client.completion(prompt)
            
            if response:
                # Parse keywords
                keywords = [
                    k.strip().lower()
                    for k in response.replace("，", ",").split(",")
                    if k.strip()
                ]
                focus_keywords = set(keywords)
                logger.debug(
                    "LLM extracted %d keywords from focus: %s",
                    len(focus_keywords),
                    focus[:50],
                )
            else:
                # Fallback to simple split
                focus_keywords = set(focus.lower().split())
        except Exception as e:
            logger.warning("LLM keyword extraction failed: %s, using simple split", e)
            focus_keywords = set(focus.lower().split())
        
        return self._prioritize_with_keywords(articles, focus, focus_keywords)

    def _prioritize_with_keywords(
        self,
        articles: list[RawArticle],
        focus: str,
        focus_keywords: Optional[set[str]] = None,
    ) -> list[RawArticle]:
        """Prioritize articles using improved keyword matching.
        
        Args:
            articles: List of articles to prioritize
            focus: User focus string (for logging)
            focus_keywords: Pre-extracted keywords (if None, will extract from focus)
            
        Returns:
            Prioritized list of articles
        """
        if focus_keywords is None:
            focus_lower = focus.lower()
            focus_keywords = set(focus_lower.split())

        def score_article(article: RawArticle) -> float:
            """Improved scoring function with word boundary matching."""
            score = 0.0

            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()
            content = article.get("content", "").lower() if article.get("content") else ""

            for keyword in focus_keywords:
                if not keyword:  # Skip empty keywords
                    continue

                # Check title with word boundary matching
                if keyword in title:
                    # Use regex to check for whole word match
                    word_pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
                    if word_pattern.search(title):
                        score += 3.0  # Whole word match in title
                    else:
                        score += 2.0  # Partial match in title

                # Check summary with word boundary matching
                if keyword in summary:
                    word_pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
                    if word_pattern.search(summary):
                        score += 2.0  # Whole word match in summary
                    else:
                        score += 1.0  # Partial match in summary

                # Check content (lower weight)
                if content and keyword in content:
                    score += 0.5

            # Bonus: Keyword density (more keywords = higher relevance)
            total_text = f"{title} {summary} {content[:200]}".lower()
            keyword_count = sum(1 for kw in focus_keywords if kw in total_text)
            if keyword_count > 0:
                score += keyword_count * 0.3  # Density bonus

            # Bonus: Shorter titles might be more focused
            if len(title) < 50:
                score += 0.2

            return score

        # Sort by score (descending)
        scored = [(article, score_article(article)) for article in articles]
        scored.sort(key=lambda x: x[1], reverse=True)

        prioritized = [article for article, _ in scored]

        logger.debug(
            "Prioritized %d articles using keyword matching (focus: %s)",
            len(prioritized),
            focus[:50],
        )

        return prioritized

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (remove extra spaces, punctuation, etc.).
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        
        # Remove common punctuation (keep only alphanumeric and spaces)
        normalized = re.sub(r"[^\w\s]", "", normalized)
        
        return normalized.strip()

    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles using Jaccard similarity.
        
        Args:
            title1: First title
            title2: Second title
            
        Returns:
            Similarity score (0-1)
        """
        if not title1 or not title2:
            return 0.0
        
        # Normalize titles
        norm1 = self._normalize_text(title1)
        norm2 = self._normalize_text(title2)
        
        if not norm1 or not norm2:
            return 0.0
        
        # If normalized titles are identical, return 1.0
        if norm1 == norm2:
            return 1.0
        
        # Calculate Jaccard similarity (word-based)
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return 0.0
        
        jaccard = intersection / union
        
        # Also check character-level similarity for short titles
        if len(norm1) < 50 or len(norm2) < 50:
            # Use simple character overlap ratio
            char_overlap = sum(1 for c in norm1 if c in norm2)
            char_ratio = char_overlap / max(len(norm1), len(norm2))
            # Combine both metrics
            return (jaccard * 0.7 + char_ratio * 0.3)
        
        return jaccard

    def deduplicate_articles(
        self,
        articles: list[RawArticle],
        title_similarity_threshold: float = 0.85,
        use_url: bool = True,
    ) -> list[RawArticle]:
        """Remove duplicate articles using multiple strategies.
        
        Uses a multi-level deduplication approach:
        1. URL-based deduplication (exact match)
        2. Title similarity-based deduplication (fuzzy match)
        
        Args:
            articles: List of articles to deduplicate
            title_similarity_threshold: Threshold for title similarity (0-1)
            use_url: Whether to use URL for exact deduplication
            
        Returns:
            Deduplicated list of articles
        """
        if not articles:
            return []
        
        deduplicated = []
        seen_urls = set()
        seen_titles = []  # List of (normalized_title, article) tuples
        
        for article in articles:
            is_duplicate = False
            
            # Strategy 1: URL-based deduplication (exact match)
            if use_url:
                url = article.get("url", "").strip()
                if url:
                    # Normalize URL (remove query params, fragments, etc. for comparison)
                    normalized_url = self._normalize_url(url)
                    if normalized_url in seen_urls:
                        is_duplicate = True
                        logger.debug("Duplicate found by URL: %s", url[:100])
                    else:
                        seen_urls.add(normalized_url)
            
            # Strategy 2: Title similarity-based deduplication (fuzzy match)
            if not is_duplicate:
                title = article.get("title", "").strip()
                if title:
                    normalized_title = self._normalize_text(title)
                    
                    # Check similarity with existing titles
                    for existing_title, existing_article in seen_titles:
                        similarity = self._title_similarity(normalized_title, existing_title)
                        if similarity >= title_similarity_threshold:
                            is_duplicate = True
                            logger.debug(
                                "Duplicate found by title similarity (%.2f): '%s' vs '%s'",
                                similarity,
                                title[:50],
                                existing_article.get("title", "")[:50],
                            )
                            break
                    
                    if not is_duplicate:
                        seen_titles.append((normalized_title, article))
            
            if not is_duplicate:
                deduplicated.append(article)
        
        removed = len(articles) - len(deduplicated)
        if removed > 0:
            logger.debug(
                "Removed %d duplicate articles (URL: %s, threshold: %.2f)",
                removed,
                use_url,
                title_similarity_threshold,
            )
        
        return deduplicated

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison.
        
        Removes query parameters, fragments, and normalizes the URL.
        
        Args:
            url: URL to normalize
            
        Returns:
            Normalized URL
        """
        if not url:
            return ""
        
        try:
            parsed = urlparse(url.lower().strip())
            # Remove query and fragment for comparison
            normalized = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path.rstrip("/"),
                    "",
                    "",
                    "",
                )
            )
            return normalized
        except Exception:
            # If URL parsing fails, just normalize the string
            return url.lower().strip()

    async def optimize_articles_for_prompt(
        self,
        articles: list[RawArticle],
        focus: str = "",
        max_tokens: int | None = None,
        max_content_length: int | None = None,
    ) -> list[RawArticle]:
        """Optimize articles for use in prompts.
        
        自动检测文章是否包含完整内容，根据实际情况进行优化。
        不需要手动指定 include_content，函数会自动处理。
        
        Applies deduplication, prioritization, and truncation.
        
        Args:
            articles: List of articles to optimize
            focus: User focus for prioritization
            max_tokens: Maximum tokens allowed
            max_content_length: Maximum length for article content (None = use default)
            
        Returns:
            Optimized list of articles
        """
        # Step 1: Deduplicate
        optimized = self.deduplicate_articles(articles)
        
        # Step 2: Prioritize (now async)
        if focus:
            optimized = await self.prioritize_articles(optimized, focus)
        
        # Step 3: Truncate (自动检测是否有内容)
        optimized = self.truncate_articles(
            optimized, max_tokens=max_tokens, max_content_length=max_content_length
        )
        
        return optimized
