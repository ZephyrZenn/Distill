from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

UILanguage = Literal["zh", "en"]


@dataclass(frozen=True)
class TraceEvent:
    key: str
    params: Mapping[str, Any] = field(default_factory=dict)


def trace_event(key: str, **params: Any) -> TraceEvent:
    return TraceEvent(key=key, params=params)


TRACE_TEMPLATES: dict[str, dict[UILanguage, str]] = {
    "task.execution.start": {
        "zh": "🚀 Agent启动，开始执行任务...",
        "en": "🚀 Agent started, beginning task execution...",
    },
    "task.execution.completed": {
        "zh": "✅ Agent执行完成，摘要已保存",
        "en": "✅ Agent finished, summary saved",
    },
    "task.execution.failed": {
        "zh": "❌ 执行失败: {error}",
        "en": "❌ Execution failed: {error}",
    },
    "task.cancelled": {
        "zh": "❌ 任务被取消",
        "en": "❌ Task was cancelled",
    },
    "task.no_articles": {
        "zh": "❌ 没有文章可用于生成简报: 请检查分组配置",
        "en": "❌ No articles are available for brief generation: please check group configuration",
    },
    "task.api_key_missing": {
        "zh": "❌ API Key 未配置: 请设置环境变量 {env_var}",
        "en": "❌ API key not configured: please set environment variable {env_var}",
    },
    "task.ps_dependency_missing": {
        "zh": "❌ PS Agent 依赖未配置: {error}",
        "en": "❌ PS Agent dependency not configured: {error}",
    },
    "workflow.start": {
        "zh": "🚀 Agent启动，获取到 {n_articles} 篇文章",
        "en": "🚀 Agent started, fetched {n_articles} articles",
    },
    "workflow.planning.start": {
        "zh": "📋 开始规划阶段...",
        "en": "📋 Starting planning stage...",
    },
    "workflow.execution.start": {
        "zh": "⚡ 开始执行阶段...",
        "en": "⚡ Starting execution stage...",
    },
    "workflow.completed": {
        "zh": "✅ Agent执行完成，共生成 {n_ok} 篇",
        "en": "✅ Agent finished, generated {n_ok} article(s)",
    },
    "planner.materials.evaluating": {
        "zh": "🔍 正在评估当前素材",
        "en": "🔍 Evaluating current materials",
    },
    "planner.articles.filtered": {
        "zh": "🔍 已筛选出 {count} 篇相关文章",
        "en": "🔍 Filtered down to {count} relevant articles",
    },
    "planner.keywords.extracted": {
        "zh": "🔍 提取到 {count} 个关键词: {keywords}",
        "en": "🔍 Extracted {count} keywords: {keywords}",
    },
    "planner.memories.found": {
        "zh": "🔍 从记忆中找到 {count} 个相关记忆: {topics}",
        "en": "🔍 Retrieved {count} related memories: {topics}",
    },
    "planner.llm.start": {
        "zh": "🤖 正在调用LLM进行规划...",
        "en": "🤖 Calling the LLM to build the plan...",
    },
    "planner.completed": {
        "zh": "🤖 规划完成：耗时 {elapsed} 秒",
        "en": "🤖 Planning completed in {elapsed} seconds",
    },
    "planner.summary": {
        "zh": "📝 规划完成：识别出 {focal_points} 个焦点话题，丢弃 {discarded} 篇文章",
        "en": "📝 Planning completed: identified {focal_points} focal topics and discarded {discarded} articles",
    },
    "planner.point.summary": {
        "zh": "   {index}. [{generation_mode}/{strategy}] {topic}",
        "en": "   {index}. [{generation_mode}/{strategy}] {topic}",
    },
    "planner.parse_failed": {
        "zh": "❌ 规划失败：无法解析LLM响应",
        "en": "❌ Planning failed: unable to parse the LLM response",
    },
    "planner.audit.progress": {
        "zh": "审计进度: {progress}",
        "en": "Audit progress: {progress}",
    },
    "executor.primary_brief.start": {
        "zh": "🧾 正在生成 1 分钟简报...",
        "en": "🧾 Generating the 1-minute brief...",
    },
    "executor.auto_deep.start": {
        "zh": "🔄 开始生成 {count} 个自动深度分析...",
        "en": "🔄 Starting generation of {count} automatic deep analyses...",
    },
    "executor.all_tasks.completed": {
        "zh": "✨ 所有任务执行完成",
        "en": "✨ All tasks completed",
    },
    "executor.optional.start": {
        "zh": "🪄 开始生成 {count} 个 Optional Analysis...",
        "en": "🪄 Starting generation of {count} Optional Analysis item(s)...",
    },
    "executor.point.failed": {
        "zh": "❌ 话题 '{topic}' 执行失败: {error}",
        "en": "❌ Topic '{topic}' execution failed: {error}",
    },
    "executor.optional_point.failed": {
        "zh": "❌ OPTIONAL_DEEP 话题 '{topic}' 执行失败: {error}",
        "en": "❌ OPTIONAL_DEEP topic '{topic}' execution failed: {error}",
    },
    "optional.process": {
        "zh": "🧩 [OPTIONAL_DEEP] 处理话题: {topic}",
        "en": "🧩 [OPTIONAL_DEEP] Processing topic: {topic}",
    },
    "optional.generating": {
        "zh": "   ↳ 正在生成 Optional Analysis 文本...",
        "en": "   ↳ Generating Optional Analysis...",
    },
    "optional.completed": {
        "zh": "   ↳ ✅ Optional 话题 '{topic}' 生成完成",
        "en": "   ↳ ✅ Optional topic '{topic}' completed",
    },
    "summarize.process": {
        "zh": "📰 [SUMMARIZE] 处理话题: {topic}",
        "en": "📰 [SUMMARIZE] Processing topic: {topic}",
    },
    "search.process": {
        "zh": "🔍 [SEARCH_ENHANCE] 处理话题: {topic}",
        "en": "🔍 [SEARCH_ENHANCE] Processing topic: {topic}",
    },
    "search.query": {
        "zh": "   ↳ 搜索扩展信息: '{query}'",
        "en": "   ↳ Searching for additional context: '{query}'",
    },
    "search.results.fetched": {
        "zh": "   ↳ 获取到 {count} 条搜索结果，正在抓取全文...",
        "en": "   ↳ Retrieved {count} search results, fetching full content...",
    },
    "search.fetch.stats": {
        "zh": "📊 抓取统计: 成功 {success}/{total}, 失败 {failed} 条",
        "en": "📊 Fetch stats: success {success}/{total}, failed {failed}",
    },
    "search.skipped": {
        "zh": "   ↳ 搜索引擎不可用，跳过搜索扩展",
        "en": "   ↳ Search engine unavailable, skipping search enhancement",
    },
    "flash.process": {
        "zh": "⚡ [FLASH_NEWS] 处理话题: {topic}",
        "en": "⚡ [FLASH_NEWS] Processing topic: {topic}",
    },
    "articles.fetching": {
        "zh": "   ↳ 获取 {count} 篇文章内容...",
        "en": "   ↳ Fetching content for {count} articles...",
    },
    "article.writing.start": {
        "zh": "   ↳ 正在撰写深度内容...",
        "en": "   ↳ Writing deep analysis...",
    },
    "flash.generating": {
        "zh": "   ↳ 正在生成快讯...",
        "en": "   ↳ Generating flash news...",
    },
    "topic.writing.completed": {
        "zh": "   ↳ ✅ 话题 '{topic}' 撰写完成",
        "en": "   ↳ ✅ Topic '{topic}' writing completed",
    },
    "flash.completed": {
        "zh": "   ↳ ✅ 快讯 '{topic}' 生成完成",
        "en": "   ↳ ✅ Flash news '{topic}' completed",
    },
    "review.approved": {
        "zh": "   ↳ ✅ 话题 '{topic}' 通过审查",
        "en": "   ↳ ✅ Topic '{topic}' passed review",
    },
    "review.approved_with_suggestions": {
        "zh": "   ↳ ✅ 话题 '{topic}' 通过审查,但有优化建议: {comment}",
        "en": "   ↳ ✅ Topic '{topic}' passed review, with optimization suggestions: {comment}",
    },
    "review.rejected_retry": {
        "zh": "   ↳ ❌ 话题 '{topic}' 未通过审查，原因: {reason}，重试 {retry} 次",
        "en": "   ↳ ❌ Topic '{topic}' did not pass review, reason: {reason}, retry {retry}",
    },
    "history.incorporating": {
        "zh": "   ↳ 获取到历史记忆，将历史记忆融入到文章中",
        "en": "   ↳ Retrieved historical memory and will incorporate it into the article",
    },
    "history.item": {
        "zh": "   ↳ 历史记忆: {topic}",
        "en": "   ↳ Historical memory: {topic}",
    },
    "ps.start": {
        "zh": "🚀 启动 Agentic Research Agent: {focus}",
        "en": "🚀 Starting Agentic Research Agent: {focus}",
    },
    "ps.failed": {
        "zh": "❌ Agent 执行失败: {error}",
        "en": "❌ Agent execution failed: {error}",
    },
    "ps.run_id": {
        "zh": "🧾 run_id={run_id}",
        "en": "🧾 run_id={run_id}",
    },
    "ps.stats": {
        "zh": "📊 运行统计: iterations={iterations} tool_calls={tool_calls} curations={curations} research_items={research_items} discarded={discarded}",
        "en": "📊 Run stats: iterations={iterations} tool_calls={tool_calls} curations={curations} research_items={research_items} discarded={discarded}",
    },
    "ps.completed": {
        "zh": "✅ 报告生成完成",
        "en": "✅ Report generated",
    },
    "ps.partial": {
        "zh": "⚠️ 未完全完成，但返回当前最优报告",
        "en": "⚠️ Not fully completed, returning the best available report",
    },
    "ps.error": {
        "zh": "❌ {error}",
        "en": "❌ {error}",
    },
    "curation.empty": {
        "zh": "[curation] 完成: 暂无可筛选素材，继续研究",
        "en": "[curation] Done: no materials to curate yet, continuing research",
    },
    "curation.stage1.start": {
        "zh": "📌 curation: 正在审核 {count} 条素材 (Stage 1)...",
        "en": "📌 curation: reviewing {count} materials (Stage 1)...",
    },
    "curation.stage1.continue": {
        "zh": "[curation] 完成: Stage1 完成 kept={kept} discarded={discarded}，继续研究",
        "en": "[curation] Done: Stage 1 complete kept={kept} discarded={discarded}, continuing research",
    },
    "curation.stage2.start": {
        "zh": "📌 curation: Stage 1 完成，正在获取全文并执行 Stage 2 深度审核 ({count} 条)...",
        "en": "📌 curation: Stage 1 complete, fetching full text and running Stage 2 deep review ({count} items)...",
    },
    "curation.content.fetched": {
        "zh": "📌 curation: 已获取 {count} 条素材的全文",
        "en": "📌 curation: fetched full text for {count} materials",
    },
    "curation.stage2.scoring": {
        "zh": "📌 curation: Stage 2 完成，正在评分 {count} 条素材",
        "en": "📌 curation: Stage 2 complete, scoring {count} materials",
    },
    "curation.completed": {
        "zh": "[curation] 完成: 审计完成，进入 plan_review",
        "en": "[curation] Done: audit completed, entering plan_review",
    },
    "plan_review.start": {
        "zh": "📌 plan_review: 正在全局评审 ({count} 条素材, iter={iteration})...",
        "en": "📌 plan_review: running global review ({count} materials, iter={iteration})...",
    },
    "plan_review.ready": {
        "zh": "[plan_review] 完成: {reason}，进入结构规划",
        "en": "[plan_review] Done: {reason}, entering structure planning",
    },
    "plan_review.patch": {
        "zh": "[plan_review] 完成: {reason}，执行补丁搜索",
        "en": "[plan_review] Done: {reason}, running patch search",
    },
    "plan_review.replan": {
        "zh": "[plan_review] 完成: {reason}，触发重新规划",
        "en": "[plan_review] Done: {reason}, triggering replanning",
    },
    "reviewing.empty": {
        "zh": "[reviewing] 失败: sections 为空，无法审稿",
        "en": "[reviewing] Failed: sections are empty, unable to review",
    },
    "reviewing.start": {
        "zh": "🧪 reviewing: 开始审稿",
        "en": "🧪 reviewing: starting review",
    },
    "reviewing.completed": {
        "zh": "[reviewing] 完成: 文章审核通过",
        "en": "[reviewing] Done: article review passed",
    },
    "reviewing.refine": {
        "zh": "[reviewing] 完成: 部分段落未通过，进入修订阶段",
        "en": "[reviewing] Done: some sections need revision, entering refine stage",
    },
    "refiner.start": {
        "zh": "[refiner] 开始修订",
        "en": "[refiner] Started refining",
    },
    "refiner.completed": {
        "zh": "[refiner] 完成: 修订完成",
        "en": "[refiner] Done: refinement completed",
    },
    "tooling.none": {
        "zh": "[tooling] 完成: 未检测到工具调用，继续研究/写作",
        "en": "[tooling] Done: no tool calls detected, continuing research/writing",
    },
    "tooling.start": {
        "zh": "[tooling] 正在执行 {count} 个搜索/检索操作...",
        "en": "[tooling] Executing {count} search/retrieval operation(s)...",
    },
    "tooling.failed": {
        "zh": "[tooling] 失败: 工具执行异常 {error}",
        "en": "[tooling] Failed: tool execution error {error}",
    },
    "writer.no_plan": {
        "zh": "[writer] 失败: 无写作指南",
        "en": "[writer] Failed: missing writing guide",
    },
    "writer.start": {
        "zh": "✍️ writer: 开始滑动窗口式写作 {count} 个章节...",
        "en": "✍️ writer: starting sliding-window writing for {count} sections...",
    },
    "writer.completed": {
        "zh": "[writer] 完成: 滑动窗口写作完成，{count} 个章节",
        "en": "[writer] Done: sliding-window writing completed, {count} sections",
    },
    "bootstrap.start": {
        "zh": "📌 bootstrap: 正在初始化研究维度与排除规则...{suffix}",
        "en": "📌 bootstrap: initializing research dimensions and exclusion rules...{suffix}",
    },
    "bootstrap.dimensions.done": {
        "zh": "📌 bootstrap: 已生成研究维度，正在生成排除关键词...",
        "en": "📌 bootstrap: research dimensions generated, creating exclusion keywords...",
    },
    "bootstrap.replan.done": {
        "zh": "[bootstrap] 完成: REPLAN 完成，重新生成 {count} 个意图维度",
        "en": "[bootstrap] Done: REPLAN completed, regenerated {count} intent dimensions",
    },
    "bootstrap.completed": {
        "zh": "[bootstrap] 完成: 已建立研究框架 focus='{focus}' dimensions={count}",
        "en": "[bootstrap] Done: research framework established focus='{focus}' dimensions={count}",
    },
    "researcher.start": {
        "zh": "🤔 planner: 正在生成搜索查询 {mode} (iter={iteration})...",
        "en": "🤔 planner: generating search queries {mode} (iter={iteration})...",
    },
    "researcher.no_queries": {
        "zh": "[planner] 完成: 未生成搜索查询，进入评审",
        "en": "[planner] Done: no search queries generated, entering review",
    },
    "researcher.completed": {
        "zh": "[planner] 完成: 已生成 {count} 个搜索查询",
        "en": "[planner] Done: generated {count} search queries",
    },
    "researcher.failed": {
        "zh": "[planner] 失败: 规划异常 {error}",
        "en": "[planner] Failed: planning error {error}",
    },
    "structure.start": {
        "zh": "📐 structuring: 正在生成写作策略...",
        "en": "📐 structuring: generating writing strategy...",
    },
    "structure.completed": {
        "zh": "[structure] 完成: {summary}",
        "en": "[structure] Done: {summary}",
    },
    "structure.failed": {
        "zh": "[structure] 失败: 规划异常 {error}",
        "en": "[structure] Failed: planning error {error}",
    },
    "finalize.start": {
        "zh": "📌 finalize: 正在完成并生成最终报告...",
        "en": "📌 finalize: completing and generating the final report...",
    },
    "finalize.completed": {
        "zh": "[finalize] 完成: status={status}",
        "en": "[finalize] Done: status={status}",
    },
}


def normalize_ui_language(language: str | None) -> UILanguage:
    value = (language or "zh").strip().lower()
    if value.startswith("en"):
        return "en"
    return "zh"


def render_trace_message(message: str | TraceEvent, ui_language: str | None) -> str:
    if isinstance(message, str):
        return message

    language = normalize_ui_language(ui_language)
    template = TRACE_TEMPLATES.get(message.key, {}).get(language)
    if template is None:
        available = ", ".join(sorted(TRACE_TEMPLATES))
        raise KeyError(f"Unknown trace key: {message.key}. Available keys: {available}")
    return template.format(**message.params)
