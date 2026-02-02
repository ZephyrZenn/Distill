import asyncio
import logging
import os
import random

import httpx
import trafilatura
from tavily import TavilyClient
from trafilatura import baseline
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

# 真实浏览器 User-Agent 池（轮换使用）
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# 基础请求头模板
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# 限流配置
MAX_CONCURRENT_REQUESTS = 5  # 降低并发数，避免触发限流
DELAY_BETWEEN_REQUESTS = (1.0, 3.0)  # 每个请求之间的随机延迟（秒）
DELAY_BETWEEN_DOMAINS = (5.0, 10.0)  # 不同域名之间的延迟（秒）

# robots.txt 缓存
_robots_cache: dict[str, RobotFileParser] = {}
_robots_cache_lock = asyncio.Lock()

# URL 内容缓存（单次 workflow 运行期间有效）
_url_content_cache: dict[str, str] = {}
_url_cache_lock = asyncio.Lock()

# 并发控制信号量
_request_semaphore: asyncio.Semaphore | None = None


def clear_url_cache():
    """清空 URL 缓存（用于测试或手动重置）."""
    global _url_content_cache
    _url_content_cache.clear()
    logger.info("[CRAWLER] 🗑️ URL 缓存已清空")


def get_headers() -> dict:
    """获取随机化的请求头."""
    headers = BASE_HEADERS.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)
    return headers


async def _can_fetch(url: str, user_agent: str = "*") -> bool:
    """检查 robots.txt 是否允许抓取."""
    try:
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        # 检查缓存
        async with _robots_cache_lock:
            if domain in _robots_cache:
                rp = _robots_cache[domain]
            else:
                rp = RobotFileParser()
                robots_url = f"{domain}/robots.txt"
                try:
                    # 使用简单的 HTTP 请求获取 robots.txt
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(robots_url, headers=get_headers())
                        if resp.status_code == 200:
                            rp.parse(resp.text.splitlines())
                        else:
                            # 无法获取 robots.txt，默认允许
                            logger.debug(
                                "[CRAWLER] robots.txt 不可用，默认允许: %s", domain
                            )
                            return True
                except Exception as e:
                    logger.debug(
                        "[CRAWLER] 获取 robots.txt 失败，默认允许: %s (%s)", domain, e
                    )
                    return True
                _robots_cache[domain] = rp

        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logger.debug("[CRAWLER] 检查 robots.txt 失败，默认允许: %s (%s)", url, e)
        return True


async def _random_delay(delay_range: tuple[float, float]) -> None:
    """随机延迟."""
    delay = random.uniform(*delay_range)
    await asyncio.sleep(delay)


def _extract_with_trafilatura(html: str, url: str) -> str | None:
    """
    使用优化后的 trafilatura 提取内容.

    优化点：
    - favor_recall=True: 提高召回率
    - include_tables=True: 保留表格
    - include_comments=False: 排除评论噪音
    - deduplicate=True: 去除重复段落
    - url: 传递 URL 帮助解析相对链接
    """
    content = trafilatura.extract(
        html,
        url=url,
        favor_recall=True,
        include_links=True,
        include_tables=True,
        include_comments=False,
        deduplicate=True,
        output_format="markdown",
    )
    return content


def _extract_with_baseline(html: str) -> str | None:
    """
    使用 baseline 作为降级提取方案.

    baseline 使用更宽松的启发式算法，适用于 extract() 失败的情况。
    """
    try:
        _, text, text_len = baseline(html)
        if text and text_len > 100:
            return text
    except Exception:
        pass
    return None


async def get_content(
    url: str, client: httpx.AsyncClient, retry_count: int = 0
) -> tuple[str, str | None, bool]:
    """
    内容获取，带重试机制.

    使用 httpx + trafilatura（优化后）+ baseline 降级

    Args:
        url: 要抓取的 URL
        client: httpx 异步客户端
        retry_count: 当前重试次数

    Returns:
        tuple: (url, content_or_None, should_retry_with_fallback)
            - should_retry_with_fallback: 是否应该用 Tavily extract 重试
    """
    # 检查 robots.txt
    if not await _can_fetch(url):
        logger.warning("[CRAWLER] 🚫 robots.txt 不允许抓取: %s", url)
        return url, None, False

    # 限流：获取信号量
    global _request_semaphore
    if _request_semaphore is None:
        _request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with _request_semaphore:
        # 添加随机延迟
        if retry_count > 0:
            # 指数退避延迟
            delay = min(2**retry_count + random.uniform(0, 1), 30)
            logger.info(
                "[CRAWLER] ⏳ 重试延迟 %.1fs (第 %d 次): %s", delay, retry_count, url
            )
            await asyncio.sleep(delay)
        else:
            await _random_delay(DELAY_BETWEEN_REQUESTS)

        # === httpx 下载 + trafilatura 提取 ===
        try:
            # 使用随机化的 headers
            resp = await client.get(
                url,
                headers=get_headers(),
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=5.0, pool=5.0),
                follow_redirects=True,
            )
            resp.raise_for_status()

            # 尝试 trafilatura 提取（优化配置）
            content = _extract_with_trafilatura(resp.text, url)

            if content:
                logger.debug("[CRAWLER] ✅ trafilatura 成功: %s", url)
                return url, content, False

            # trafilatura 失败，尝试 baseline 降级
            logger.debug("[CRAWLER] 🔄 trafilatura 失败，尝试 baseline: %s", url)
            content = _extract_with_baseline(resp.text)

            if content:
                logger.info("[CRAWLER] ✅ baseline 降级成功: %s", url)
                return url, content, False

            logger.warning("[CRAWLER] ⚠️ 内容提取失败 (trafilatura + baseline): %s", url)
            # 内容提取失败可以尝试 Tavily
            return url, None, True

        except httpx.TimeoutException:
            logger.warning("[CRAWLER] ⏱️ 请求超时: %s", url)
            # 超时可以尝试 Tavily
            return url, None, True

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("[CRAWLER] ❌ HTTP错误 %d: %s", status, url)

            # 404, 5xx 不重试
            if status == 404 or status >= 500:
                return url, None, False

            # 429 Too Many Requests - 限流，使用指数退避重试
            if status == 429 and retry_count < 3:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = int(retry_after)
                    except ValueError:
                        delay = 60
                else:
                    delay = 2 ** (retry_count + 2) + random.uniform(0, 5)

                logger.info(
                    "[CRAWLER] 🔄 触发限流，等待 %ds 后重试: %s", int(delay), url
                )
                await asyncio.sleep(delay)
                return await get_content(url, client, retry_count + 1)

            # 其他 4xx 错误可以尝试 Tavily
            return url, None, True

        except httpx.RequestError as exc:
            logger.warning(
                "[CRAWLER] 🔌 网络请求失败 (%s): %s", type(exc).__name__, url
            )
            # 网络错误可以尝试 Tavily
            return url, None, True

        except Exception as exc:
            logger.error(
                "[CRAWLER] 💥 未知错误 (%s: %s): %s", type(exc).__name__, exc, url
            )
            return url, None, False


async def fetch_all_contents(urls: list[str]) -> dict[str, str]:
    """
    使用异步 IO 批量抓取，带域名分组优化和 URL 缓存.

    新的兜底策略：
    1. 检查缓存，命中则直接返回
    2. httpx 并发获取未缓存的 URL 正文
    3. 收集失败的 URL（排除 404 和 5xx）
    4. 使用 Tavily extract 批量获取失败的 URL
    5. 更新缓存

    优化策略：
    - URL 缓存：避免重复抓取相同 URL
    - 按 domain 分组
    - 同域名串行或低并发（避免被封）
    - 不同域名之间添加延迟
    - 共享 httpx 连接池
    """
    if not urls:
        return {}

    # 去重
    unique_urls = list(dict.fromkeys(urls))  # 保持顺序的去重

    # 检查缓存
    async with _url_cache_lock:
        cached_results = {url: _url_content_cache[url] for url in unique_urls if url in _url_content_cache}

    if cached_results:
        logger.info("[CRAWLER] 💾 缓存命中: %d/%d URLs", len(cached_results), len(unique_urls))

    # 只需要抓取未缓存的 URLs
    uncached_urls = [url for url in unique_urls if url not in cached_results]

    if not uncached_urls:
        return cached_results

    # 按 domain 分组未缓存的 URLs
    from collections import defaultdict

    domain_groups: dict[str, list[str]] = defaultdict(list)
    for url in uncached_urls:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or "unknown"
            domain_groups[domain].append(url)
        except Exception:
            domain_groups["unknown"].append(url)

    logger.info(
        "[CRAWLER] 📊 分组统计: %d 个域名, %d 个未缓存 URL", len(domain_groups), len(uncached_urls)
    )

    # 使用异步 Client 共享连接池（降低最大连接数）
    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        timeout=httpx.Timeout(30.0),
    ) as client:
        new_results = {}
        failed_urls_for_tavily: list[str] = []

        # === 第一步：httpx 获取所有未缓存的 URL ===
        for i, (domain, domain_urls) in enumerate(domain_groups.items()):
            logger.info(
                "[CRAWLER] 🌐 处理域名 [%d/%d]: %s (%d URLs)",
                i + 1,
                len(domain_groups),
                domain,
                len(domain_urls),
            )

            # 同域名的 URL 并行处理（限制并发数为 2-3，避免触发限流）
            # 使用 asyncio.Semaphore 控制并发
            domain_semaphore = asyncio.Semaphore(2)  # 每个域名最多 2 个并发请求

            async def fetch_with_semaphore(url: str) -> tuple[str, str | None, bool]:
                async with domain_semaphore:
                    return await get_content(url, client)

            # 并行获取同一域名的所有 URL
            domain_tasks = [fetch_with_semaphore(url) for url in domain_urls]
            domain_results = await asyncio.gather(*domain_tasks, return_exceptions=True)

            for result in domain_results:
                if isinstance(result, Exception):
                    logger.error("[CRAWLER] 💥 域名抓取异常: %s", result)
                    continue

                url, content, should_retry = result
                if content:
                    new_results[url] = content
                elif should_retry:
                    failed_urls_for_tavily.append(url)

            # 域名之间的延迟（除了最后一个）
            if i < len(domain_groups) - 1:
                await _random_delay(DELAY_BETWEEN_DOMAINS)
                logger.info("[CRAWLER] ⏸️ 域名间延迟，等待下一个域名...")

        logger.info("[CRAWLER] 📊 httpx 阶段完成: 成功 %d/%d, 失败 %d",
                   len(new_results), len(uncached_urls), len(failed_urls_for_tavily))

        # === 第二步：使用 Tavily extract 获取失败的 URL ===
        if failed_urls_for_tavily:
            tavily_api_key = os.getenv("TAVILY_API_KEY")
            if tavily_api_key:
                logger.info("[CRAWLER] 🔄 使用 Tavily extract 获取 %d 个失败的 URL", len(failed_urls_for_tavily))
                tavily_results = await _extract_with_tavily(failed_urls_for_tavily, tavily_api_key)
                new_results.update(tavily_results)
                logger.info("[CRAWLER] 📊 Tavily 阶段完成: 成功 %d/%d", len(tavily_results), len(failed_urls_for_tavily))
            else:
                logger.warning("[CRAWLER] ⚠️ TAVILY_API_KEY 未设置，跳过 Tavily extract")

        # === 第三步：更新缓存 ===
        if new_results:
            async with _url_cache_lock:
                _url_content_cache.update(new_results)
            logger.info("[CRAWLER] 💾 更新缓存: %d 条", len(new_results))

        # === 第四步：合并缓存和新获取的结果 ===
        final_results = {**cached_results, **new_results}
        logger.info("[CRAWLER] ✅ 抓取完成: 缓存 %d + 新获取 %d = 总计 %d/%d",
                   len(cached_results), len(new_results), len(final_results), len(unique_urls))
        return final_results


async def _extract_with_tavily(urls: list[str], api_key: str) -> dict[str, str]:
    """
    使用 Tavily extract 批量获取 URL 内容.

    Args:
        urls: 要提取的 URL 列表
        api_key: Tavily API key

    Returns:
        dict: {url: content} 映射
    """
    if not urls:
        return {}

    try:
        client = TavilyClient(api_key=api_key)

        # Tavily extract 支持批量查询（最多 20 个 URL）
        batch_size = 20
        results = {}

        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            logger.info("[CRAWLER] 📦 Tavily extract 批次 %d/%d, URL 数量: %d",
                      (i // batch_size) + 1, (len(urls) + batch_size - 1) // batch_size, len(batch))

            try:
                response = client.extract(urls=batch)

                # 解析响应
                if response and "results" in response:
                    for result in response["results"]:
                        url = result.get("url", "")
                        content = result.get("raw_content", "") or result.get("content", "")
                        if url and content:
                            results[url] = content
                            logger.debug("[CRAWLER] ✅ Tavily extract 成功: %s", url)
                        else:
                            logger.warning("[CRAWLER] ⚠️ Tavily extract 返回空内容: %s", url)

                # 记录失败的 URL
                extracted_urls = set(results.keys())
                for url in batch:
                    if url not in extracted_urls:
                        logger.warning("[CRAWLER] ❌ Tavily extract 失败: %s", url)

            except Exception as exc:
                logger.error("[CRAWLER] 💥 Tavily extract 批次失败: %s", exc)
                # 继续处理下一批

        return results

    except Exception as exc:
        logger.error("[CRAWLER] 💥 Tavily extract 初始化失败: %s", exc)
        return {}
