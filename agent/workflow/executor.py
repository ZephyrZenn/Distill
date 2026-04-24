import asyncio
import logging
from typing import Literal

from agent.models import (
    AgentCriticResult,
    AgentState,
    FocalPoint,
    WritingMaterial,
    log_step,
)
from agent.tools import (
    fetch_web_contents,
    get_article_content,
    is_search_engine_available,
    search_web,
)
from agent.tools.writing_tool import (
    review_article,
    write_article,
    write_optional_section,
    write_primary_brief,
)
from agent.workflow.expansion import build_expandable_topics
from agent.workflow.layered import (
    assemble_layered_report,
    get_auto_deep_points,
    get_optional_deep_points,
    normalize_plan_layers,
)
from agent.tracing import trace_event
from core.llm_client import LLMClient
from core.models.search import SearchResult

logger = logging.getLogger(__name__)


def _ext_info_dedupe_key(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    return (url or f"title::{title}").lower()


def _append_ext_info_deduped(state: AgentState, new_results: list[SearchResult]) -> None:
    """将搜索结果并入 state['ext_info']，与已有条目按 URL / 标题去重（多 focal SEARCH_ENHANCE 时避免重复）。"""
    if "ext_info" not in state:
        state["ext_info"] = []
    seen = {
        _ext_info_dedupe_key(x)
        for x in state["ext_info"]
        if isinstance(x, dict)
    }
    for r in new_results:
        if not isinstance(r, dict):
            continue
        key = _ext_info_dedupe_key(r)
        if not key or key in seen:
            continue
        seen.add(key)
        state["ext_info"].append(r)


class AgentExecutor:
    def __init__(self, client: LLMClient, max_retries: int = 3):
        self.client = client
        self.max_retries = max_retries

    async def execute(self, state: AgentState) -> list[tuple[str, bool]]:
        plan = state["plan"]
        focal_points = plan.get("focal_points", [])
        logger.info(
            "[workflow:executor] execute() start focal_points=%d",
            len(focal_points),
        )
        article_ids = [article["id"] for article in state["scored_articles"]]
        db_articles = await get_article_content(article_ids)
        for article in state["scored_articles"]:
            if article["id"] in db_articles:
                article["content"] = db_articles[article["id"]]
        normalized_plan = normalize_plan_layers(plan)
        state["plan"] = normalized_plan
        focal_points = normalized_plan.get("focal_points", [])
        auto_deep_points = get_auto_deep_points(normalized_plan)
        optional_points = get_optional_deep_points(normalized_plan)
        state["expandable_topics"] = build_expandable_topics(normalized_plan)
        logger.info(
            "[workflow:executor] layered routing total=%d auto_deep=%d optional=%d",
            len(focal_points),
            len(auto_deep_points),
            len(optional_points),
        )

        async def run_point(point: FocalPoint) -> tuple[str, bool]:
            topic = point.get("topic", "")
            strategy = point.get("strategy", "")
            logger.info(
                "[workflow:executor] point start topic=%s strategy=%s",
                topic[:48],
                strategy,
            )
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
                logger.info("[workflow:executor] point done topic=%s ok=1", topic[:48])
                return (result, True)
            except Exception as e:  # noqa: BLE001
                log_step(
                    state,
                    trace_event("executor.point.failed", topic=point["topic"], error=e),
                )
                logger.exception(
                    "[workflow:executor] point failed topic=%s strategy=%s error=%s",
                    topic[:48],
                    strategy,
                    e,
                )
                # Return a placeholder so the layered brief can still be assembled.
                error_result = f"[FAILED] {point['topic']}: {e}"
                return (error_result, False)

        async def run_optional_point(point: FocalPoint) -> tuple[str, bool]:
            topic = point.get("topic", "")
            logger.info("[workflow:executor] optional point start topic=%s", topic[:48])
            try:
                result = await self.handle_optional_deep(point, state)
                logger.info("[workflow:executor] optional point done topic=%s ok=1", topic[:48])
                return (result, True)
            except Exception as e:  # noqa: BLE001
                log_step(
                    state,
                    trace_event(
                        "executor.optional_point.failed",
                        topic=point["topic"],
                        error=e,
                    ),
                )
                logger.exception(
                    "[workflow:executor] optional point failed topic=%s error=%s",
                    topic[:48],
                    e,
                )
                return (f"[FAILED_OPTIONAL] {point['topic']}: {e}", False)

        log_step(state, trace_event("executor.primary_brief.start"))
        primary_brief = await write_primary_brief(
            self.client,
            normalized_plan,
            target_language=state.get("target_language", "zh"),
        )

        tasks = []
        log_step(
            state,
            trace_event("executor.auto_deep.start", count=len(auto_deep_points)),
        )
        for point in auto_deep_points:
            tasks.append(run_point(point))

        results = await asyncio.gather(*tasks, return_exceptions=False) if tasks else []
        n_ok = sum(1 for _, success in results if success)
        n_fail = len(results) - n_ok
        logger.info(
            "[workflow:executor] execute() done auto_deep=%d success=%d fail=%d",
            len(results),
            n_ok,
            n_fail,
        )
        log_step(state, trace_event("executor.all_tasks.completed"))
        deep_sections = [result for result, success in results if success]
        failed_sections = [result for result, success in results if not success]
        if failed_sections:
            deep_sections.extend(failed_sections)

        optional_tasks = []
        if optional_points:
            log_step(
                state,
                trace_event("executor.optional.start", count=len(optional_points)),
            )
            optional_tasks = [run_optional_point(point) for point in optional_points]
        optional_results = (
            await asyncio.gather(*optional_tasks, return_exceptions=False)
            if optional_tasks
            else []
        )
        optional_sections = [
            result for result, success in optional_results if success or result
        ]

        final_report = assemble_layered_report(
            primary_brief=primary_brief,
            deep_sections=deep_sections,
            optional_sections=optional_sections,
        )
        overall_success = all(success for _, success in results) if results else True
        state["summary_results"] = [final_report]
        state["execution_status"] = [overall_success]
        return [(final_report, overall_success)]

    async def handle_optional_deep(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, trace_event("optional.process", topic=point["topic"]))
        writing_material = self.build_writing_material(point, state, "DEEP")
        log_step(state, trace_event("optional.generating"))
        result = await write_optional_section(self.client, writing_material)
        log_step(state, trace_event("optional.completed", topic=point["topic"]))
        return result

    async def handle_summarize(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, trace_event("summarize.process", topic=point["topic"]))
        writing_material = self.build_writing_material(point, state, "DEEP")
        log_step(state, trace_event("article.writing.start"))
        result = await self.write_with_review(writing_material, state, point)
        log_step(state, trace_event("topic.writing.completed", topic=point["topic"]))
        return result

    async def handle_search_enhance(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, trace_event("search.process", topic=point["topic"]))

        if is_search_engine_available():
            log_step(state, trace_event("search.query", query=point["search_query"]))
            # 不获取 raw_content，仅获取摘要
            search_results = await search_web(
                point["search_query"], include_raw_content=False
            )
            total = len(search_results)

            log_step(state, trace_event("search.results.fetched", count=total))

            # 抓取所有搜索结果的全文
            urls = [result["url"] for result in search_results]
            contents = await fetch_web_contents(urls)
            for result in search_results:
                fetched_content = contents.get(result["url"], "")
                if fetched_content:
                    result["content"] = fetched_content

            # 过滤掉没有内容的结果
            search_results = [r for r in search_results if r.get("content")]
            success = len(search_results)
            failed = total - success
            log_step(
                state,
                trace_event(
                    "search.fetch.stats",
                    success=success,
                    total=total,
                    failed=failed,
                ),
            )
            # 收集外部搜索结果到 state（与已有 ext_info 去重）
            _append_ext_info_deduped(state, search_results)
        else:
            log_step(state, trace_event("search.skipped"))
            search_results = []

        writing_material = self.build_writing_material(
            point, state, "DEEP", search_results
        )
        log_step(state, trace_event("article.writing.start"))
        result = await self.write_with_review(writing_material, state, point)
        log_step(state, trace_event("topic.writing.completed", topic=point["topic"]))
        return result

    async def handle_flash_news(self, point: FocalPoint, state: AgentState) -> str:
        log_step(state, trace_event("flash.process", topic=point["topic"]))
        raw_articles = [
            article
            for article in state["raw_articles"]
            if article["id"] in point["article_ids"]
        ]
        log_step(state, trace_event("articles.fetching", count=len(raw_articles)))
        writing_material = self.build_writing_material(point, state, style="FLASH")
        log_step(state, trace_event("flash.generating"))
        result = await self._write_article(writing_material)
        log_step(state, trace_event("flash.completed", topic=point["topic"]))
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
                log_step(state, trace_event("review.approved", topic=point["topic"]))
                break
            if not has_critical_error and not review["status"] == "REJECTED":
                log_step(
                    state,
                    trace_event(
                        "review.approved_with_suggestions",
                        topic=point["topic"],
                        comment=review["overall_comment"],
                    ),
                )
                break
            log_step(
                state,
                trace_event(
                    "review.rejected_retry",
                    topic=point["topic"],
                    reason=review["decision_logic"],
                    retry=count + 1,
                ),
            )
            count += 1
        return result

    async def _write_article(
        self, writing_material: WritingMaterial, review: AgentCriticResult | None = None
    ) -> str:
        """撰写文章"""
        return await write_article(
            client=self.client,
            writing_material=writing_material,
            review=review,
        )

    async def _review_article(
        self, draft_content: str, material: WritingMaterial
    ) -> AgentCriticResult:
        """审查文章"""
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
        """
        构建 WritingMaterial 对象

        Args:
            point: FocalPoint 对象
            state: AgentState 对象
            style: 文章风格
        Returns:
            WritingMaterial 实例
        """
        scored_articles = [
            article
            for article in state["scored_articles"]
            if article["id"] in point["article_ids"]
        ]
        log_step(state, trace_event("articles.fetching", count=len(scored_articles)))
        history_memory_ids = point.get("history_memory_id", [])
        history_memory = [
            state["history_memories"][hid]
            for hid in history_memory_ids
            if hid in state["history_memories"]
        ]
        if history_memory:
            log_step(state, trace_event("history.incorporating"))
            for memory in history_memory:
                log_step(state, trace_event("history.item", topic=memory["topic"]))
        writing_material = WritingMaterial(
            topic=point["topic"],
            style=style,
            match_type=point["match_type"],
            relevance_description=point["relevance_description"],
            writing_guide=point.get("writing_guide", ""),
            reasoning=point["reasoning"],
            articles=scored_articles,
            history_memory=history_memory if history_memory else [],
            ext_info=ext_info if ext_info else [],
            target_language=state.get("target_language", "zh"),
        )
        return writing_material
