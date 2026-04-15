import logging
from datetime import datetime
import json
import time
from agent.models import AgentPlanResult, AgentState, Article, RawArticle, log_step
from agent.prompts import PLANNER_USER_PROMPT, PLANNER_SYSTEM_PROMPT
from agent.utils import extract_json
from agent.tools import find_keywords_with_llm, search_memory
from agent.workflow.layered import normalize_plan_layers
from core.llm_client import LLMClient
from core.models.llm import Message

logger = logging.getLogger(__name__)


class AgentPlanner:
    def __init__(
        self, client: LLMClient, batch_size: int = 20, max_article_count: int = 30
    ):
        self.client = client
        self.batch_size = batch_size
        self.max_article_count = max_article_count

    async def plan(self, state: AgentState) -> AgentPlanResult:
        result = None
        n_raw = len(state.get("raw_articles", []))
        logger.info("[workflow:planner] plan() start raw_articles=%d", n_raw)
        log_step(state, "🔍 正在评估当前素材")
        ranked_articles = await self._rank_articles(
            state["raw_articles"], state["focus"], state
        )
        log_step(state, f"🔍 已筛选出 {len(ranked_articles)} 篇相关文章")
        state["scored_articles"] = ranked_articles
        logger.info("[workflow:planner] rank_articles done kept=%d", len(ranked_articles))
        keywords = await find_keywords_with_llm(self.client, state["scored_articles"])
        log_step(state, f"🔍 提取到 {len(keywords)} 个关键词: {keywords}")
        memories = await search_memory(keywords)
        memory_topics = [m["topic"] for m in memories.values()] if memories else []
        log_step(state, f"🔍 从记忆中找到 {len(memories)} 个相关记忆: {memory_topics}")
        state["history_memories"] = memories
        logger.info("[workflow:planner] keywords=%d memories=%d", len(keywords), len(memories))

        log_step(state, "🤖 正在调用LLM进行规划...")
        prompt = await self._build_prompt(state)
        logger.info("[workflow:planner] sending prompt to LLM len=%d", len(prompt) if isinstance(prompt, (str, list)) else 0)
        start_time = time.time()
        response = await self.client.completion(prompt)
        elapsed = time.time() - start_time
        log_step(state, f"🤖 规划完成：耗时 {elapsed} 秒")
        logger.info("[workflow:planner] LLM response received elapsed=%.2fs response_len=%d", elapsed, len(response) if isinstance(response, str) else 0)
        try:
            result: AgentPlanResult = normalize_plan_layers(extract_json(response))
            n_focal = len(result.get("focal_points", []))
            logger.info("[workflow:planner] plan() done focal_points=%d discarded=%d", n_focal, len(result.get("discarded_items", [])))
            for point in result["focal_points"]:
                point["article_ids"] = [str(aid) for aid in point["article_ids"]]
            state["plan"] = result
            focal_points = result.get("focal_points", [])
            discarded = result.get("discarded_items", [])
            log_step(
                state,
                f"📝 规划完成：识别出 {len(focal_points)} 个焦点话题，丢弃 {len(discarded)} 篇文章",
            )
            for i, point in enumerate(focal_points, 1):
                generation_mode = point.get("generation_mode", "BRIEF_ONLY")
                log_step(state, f"   {i}. [{generation_mode}/{point['strategy']}] {point['topic']}")
            return result
        except json.JSONDecodeError as e:
            log_step(state, "❌ 规划失败：无法解析LLM响应")
            logger.error("[workflow:planner] parse failed response_len=%d error=%s", len(response) if isinstance(response, str) else 0, e)
            raise ValueError(f"Failed to parse planner response: {response}") from e

    async def _rank_articles(
        self, articles: list[RawArticle], focus: str, state: AgentState
    ) -> list[Article]:
        """使用 LLM 批量打分文章相关性，并按分数排序。

        Args:
            articles: 待排序的文章列表
            focus: 用户关注点
            batch_size: 每批处理的文章数量（默认 20）

        Returns:
            按相关性分数排序的文章列表
        """
        if not articles or not focus:
            logger.info("[workflow:planner] _rank_articles skip articles=%d focus_empty=%s", len(articles), not focus)
            return articles
        batch_size = self.batch_size
        scored_articles = []
        logger.info("[workflow:planner] _rank_articles start total=%d batch_size=%d", len(articles), batch_size)

        # 分批处理
        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            logger.info(
                "[workflow:planner] batch score batch_index=%d batch_len=%d",
                i // batch_size + 1, len(batch),
            )

            # 构建简化的文章信息
            articles_info = []
            for article in batch:
                articles_info.append(
                    {
                        "id": article.get("id", ""),
                        "title": article.get("title", ""),
                        "summary": article.get("summary", "")[:100],
                    }
                )

            # 构建打分 prompt
            prompt = f"""# Role
你是一位资深的情报分析专家，擅长从复杂信息中识别“特定需求匹配度”与“行业全局影响力”。

# Task
请对【文章列表】进行多维度评估，旨在筛选出既符合【用户关注点】，又具备【高情报价值】的内容。

# Scoring Logic (双轨取最高原则)
最终得分取以下两个维度中的**最高分**：

## 维度 A：用户关注点匹配度 (0-10分)
- **9-10分**：直接命中核心关注点，提供决策级信息。
- **6-8分**：属于关注点的延伸话题或重要补充。
- **3-5分**：提及相关概念，但属于边缘信息。

## 维度 B：全局价值/重点事件 (0-10分) - **重要**
无论是否符合关注点，若具备以下特征，请给高分：
- **行业风向标 (8-10分)**：如巨头重大战略转型、行业顶层政策突发变动、市场格局重塑。
- **重磅突破 (8-10分)**：如颠覆性技术发布、IPO/巨额融资、学术界里程碑。
- **风险/预警 (7-9分)**：行业性系统风险、重大安全漏洞或负面舆情。

# Constraints
1. **平衡策略**：若文章与关注点无关，但属于“维度 B”中的重点事件，必须给予高分并在理由中说明其全局价值。
2. **输出要求**：仅输出 JSON，不含任何解释。

# Input Data
- 用户关注点：{focus}
- 文章列表：{articles_info}

# Output Format
{{
  "scores": [
    {{
      "id": "文章ID",
      "score": 最终得分,
      "reasoning": "说明得分依据（是基于用户关注点命中，还是基于事件本身的行业权重）"
    }}
  ]
}}
"""

            try:
                response = await self.client.completion([Message.user(content=prompt)])
                scores_data = extract_json(response)
                res = {
                    s["id"]: {"score": s["score"], "reasoning": s["reasoning"]}
                    for s in scores_data.get("scores", [])
                }
                # 为当前批次的文章添加分数
                for article in batch:
                    article_id = str(article["id"])
                    score = res.get(article_id, {}).get("score", 0)
                    reasoning = res.get(article_id, {}).get("reasoning", "")
                    scored_articles.append(
                        Article(
                            id=article_id,
                            title=article.get("title", ""),
                            url=article.get("url", ""),
                            summary=article.get("summary", ""),
                            pub_date=article.get("pub_date", ""),
                            score=score,
                            reasoning=reasoning,
                        )
                    )

                batch_scores = [a["score"] for a in scored_articles[-len(batch) :]]
                logger.info(
                    "[workflow:planner] batch done batch_index=%d avg=%.1f min=%d max=%d",
                    i // batch_size + 1,
                    sum(batch_scores) / len(batch) if batch else 0,
                    min(batch_scores) if batch_scores else 0,
                    max(batch_scores) if batch_scores else 0,
                )

            except Exception as e:
                logger.error("[workflow:planner] batch score failed batch_index=%d error=%s", i // batch_size + 1, e)
                # 如果打分失败，给这批文章默认分数 0
                for article in batch:
                    scored_articles.append(
                        Article(
                            id=article.get("id", ""),
                            title=article.get("title", ""),
                            url=article.get("url", ""),
                            summary=article.get("summary", ""),
                            pub_date=article.get("pub_date", ""),
                            score=0,
                            reasoning="",
                        )
                    )
            progress = len(scored_articles) / len(articles)
            log_step(state, f"审计进度: {progress:.2%}")
        # 按分数降序排序
        scored_articles.sort(key=lambda a: a["score"], reverse=True)
        if len(scored_articles) > self.max_article_count:
            scored_articles = scored_articles[: self.max_article_count]
        # 过滤低分文章（score < 3）
        scored_articles = [a for a in scored_articles if a["score"] >= 3]

        logger.info(
            "[workflow:planner] _rank_articles done total=%d kept=%d discarded=%d",
            len(articles), len(scored_articles), len(articles) - len(scored_articles),
        )

        return scored_articles

    async def _build_prompt(self, state: AgentState) -> list[Message]:

        # 格式化文章为JSON字符串（只包含关键信息）
        articles_json = json.dumps(
            [
                {
                    "id": str(a.get("id", "")),
                    "title": a.get("title", ""),
                    "url": a.get("url", ""),
                    "summary": a.get("summary", ""),
                    "pub_date": str(a.get("pub_date", "")),
                    "score": a.get("score", 0),
                    "reasoning": a.get("reasoning", ""),
                }
                for a in state["scored_articles"]
            ],
            ensure_ascii=False,
            indent=2,
        )

        # 优化历史记忆
        history_memories_list = list(state["history_memories"].values())

        history_memories = [
            {
                "id": memory["id"],
                "topic": memory["topic"],
                "reasoning": memory.get("reasoning", ""),
            }
            for memory in history_memories_list
        ]
        system_prompt = Message.system(content=PLANNER_SYSTEM_PROMPT)
        system_prompt.set_priority(0)
        user_prompt = Message.user(
            content=PLANNER_USER_PROMPT.format(
                current_date=datetime.now().strftime("%Y-%m-%d"),
                focus=state.get("focus", ""),
                articles=articles_json,
                history_memories=json.dumps(
                    history_memories, ensure_ascii=False, indent=2
                ),
            ),
        )
        user_prompt.set_priority(0)
        return [
            system_prompt,
            user_prompt,
        ]
