import asyncio
import logging
from typing import Literal
from agent.models import (
    AgentState,
    FocalPoint,
    WritingMaterial,
    AgentCriticResult,
    log_step,
)
from agent.tools.search_tool import (
    search_web,
    fetch_web_contents,
    is_search_engine_available,
)
from agent.tools.writing_tool import write_article, review_article
from distill_lib.providers import (
    InMemoryWorkflowArticleContentProvider,
    WorkflowArticleContentProvider,
)
from core.llm_client import LLMClient
from core.models.search import SearchResult

logger = logging.getLogger(__name__)


class AgentExecutor:

    def __init__(
        self,
        client: LLMClient,
        max_retries: int = 3,
        article_content_provider: WorkflowArticleContentProvider | None = None,
    ):
        self.client = client
        self.max_retries = max_retries
        self.article_content_provider = (
            article_content_provider
            or InMemoryWorkflowArticleContentProvider(article_contents={})
        )

    async def execute(self, state: AgentState) -> list[tuple[str, bool]]:
        plan = state["plan"]
        article_ids = [article["id"] for article in state["scored_articles"]]
        db_articles = await self.article_content_provider.get_article_content(article_ids)
        for article in state["scored_articles"]:
            if article["id"] in db_articles:
                article["content"] = db_articles[article["id"]]
        tasks = []
        log_step(state, f"🔄 开始并行执行 {len(plan['focal_points'])} 个任务...")

        async def run_point(point: FocalPoint) -> tuple[str, bool]:
            try:
                result = None
                if point["strategy"] == "SUMMARIZE":
                    result = await self.handle_summarize(point, state)
                elif point["strategy"] == "SEARCH_ENHANCE":
                    result = await self.handle_search_enhance(point, state)
                elif point["strategy"] == "FLASH_NEWS":
                    result = await self.handle_flash_news(point, state)
                else:
                    raise ValueError(f"未知策略: {point['strategy']}")
                return (result, True)
            except Exception as e:  # noqa: BLE001
                msg = f"❌ 话题 '{point['topic']}' 执行失败: {e}"
                log_step(state, msg)
                logger.exception(msg)
                error_result = f"[FAILED] {point['topic']}: {e}"
                return (error_result, False)

        for point in plan["focal_points"]:
            tasks.append(run_point(point))

        results = await asyncio.gather(*tasks, return_exceptions=False)
        log_step(state, "✨ 所有任务执行完成")
        state["summary_results"] = [result for result, _ in results]
        state["execution_status"] = [success for _, success in results]
        return results

    async def handle_summarize(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, f"📰 [SUMMARIZE] 处理话题: {point['topic']}")
        writing_material = self.build_writing_material(point, state, "DEEP")
        log_step(state, "   ↳ 正在撰写深度内容...")
        result = await self.write_with_review(writing_material, state, point)
        log_step(state, f"   ↳ ✅ 话题 '{point['topic']}' 撰写完成")
        return result

    async def handle_search_enhance(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, f"🔍 [SEARCH_ENHANCE] 处理话题: {point['topic']}")

        if is_search_engine_available():
            log_step(state, f"   ↳ 搜索扩展信息: '{point['search_query']}'")
            search_results = await search_web(
                point["search_query"], include_raw_content=False
            )
            total = len(search_results)

            log_step(state, f"   ↳ 获取到 {total} 条搜索结果，正在抓取全文...")

            urls = [result["url"] for result in search_results]
            contents = await fetch_web_contents(urls)
            for result in search_results:
                fetched_content = contents.get(result["url"], "")
                if fetched_content:
                    result["content"] = fetched_content

            search_results = [r for r in search_results if r.get("content")]
            success = len(search_results)
            failed = total - success
            log_step(state, f"📊 抓取统计: 成功 {success}/{total}, 失败 {failed} 条")
            if "ext_info" not in state:
                state["ext_info"] = []
            state["ext_info"].extend(search_results)
        else:
            log_step(state, "   ↳ 搜索引擎不可用，跳过搜索扩展")
            search_results = []

        writing_material = self.build_writing_material(
            point, state, "DEEP", search_results
        )
        log_step(state, "   ↳ 正在撰写深度内容...")
        result = await self.write_with_review(writing_material, state, point)
        log_step(state, f"   ↳ ✅ 话题 '{point['topic']}' 撰写完成")
        return result

    async def handle_flash_news(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, f"⚡ [FLASH_NEWS] 处理话题: {point['topic']}")
        raw_articles = [
            article
            for article in state["raw_articles"]
            if article["id"] in point["article_ids"]
        ]
        log_step(state, f"   ↳ 获取 {len(raw_articles)} 篇文章内容...")
        writing_material = self.build_writing_material(point, state, style="FLASH")
        log_step(state, "   ↳ 正在生成快讯...")
        result = await self._write_article(writing_material)
        log_step(state, f"   ↳ ✅ 快讯 '{point['topic']}' 生成完成")
        return result

    async def write_with_review(
        self, writing_material: WritingMaterial, state: AgentState, point: FocalPoint
    ) -> str:
        count = 0
        review = None
        while count < self.max_retries:
            result = await self._write_article(writing_material, review)
            review = await self._review_article(result, writing_material)
            has_critical_error = any(
                finding["severity"] == "CRITICAL" for finding in review["findings"]
            )
            if review["status"] == "APPROVED":
                log_step(state, f"   ↳ ✅ 话题 '{point['topic']}' 通过审查")
                break
            if not has_critical_error and not review["status"] == "REJECTED":
                log_step(
                    state,
                    f"   ↳ ✅ 话题 '{point['topic']}' 通过审查,但有优化建议: {review['overall_comment']}",
                )
                break
            log_step(
                state,
                f"   ↳ ❌ 话题 '{point['topic']}' 未通过审查，原因: {review['decision_logic']}，重试 {count + 1} 次",
            )
            count += 1
        return result

    async def _write_article(
        self, writing_material: WritingMaterial, review: AgentCriticResult | None = None
    ) -> str:
        return await write_article(
            client=self.client,
            writing_material=writing_material,
            review=review,
        )

    async def _review_article(
        self, draft_content: str, material: WritingMaterial
    ) -> AgentCriticResult:
        return await review_article(
            client=self.client,
            draft_content=draft_content,
            writing_material=material,
        )

    def build_writing_material(
        self,
        point: FocalPoint,
        state: AgentState,
        style: Literal["DEEP", "FLASH"],
        ext_info: list[SearchResult] | None = None,
    ) -> WritingMaterial:
        scored_articles = [
            article
            for article in state["scored_articles"]
            if article["id"] in point["article_ids"]
        ]
        log_step(state, f"   ↳ 获取 {len(scored_articles)} 篇文章内容...")
        history_memory_ids = point.get("history_memory_id", [])
        history_memory = [
            state["history_memories"][hid]
            for hid in history_memory_ids
            if hid in state["history_memories"]
        ]
        if history_memory:
            log_step(state, "   ↳ 获取到历史记忆，将历史记忆融入到文章中")
            for memory in history_memory:
                log_step(state, f"   ↳ 历史记忆: {memory['topic']}")
        writing_material = WritingMaterial(
            topic=point["topic"],
            style=style,
            match_type=point["match_type"],
            relevance_description=point["relevance_description"],
            writing_guide=point["writing_guide"],
            reasoning=point["reasoning"],
            articles=scored_articles,
            history_memory=history_memory if history_memory else [],
            ext_info=ext_info if ext_info else [],
        )
        return writing_material
