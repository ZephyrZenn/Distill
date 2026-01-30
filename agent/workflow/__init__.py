import logging
from typing import Optional
from agent.models import AgentState, RawArticle, StepCallback, log_step
from agent.tools import get_recent_group_update, save_current_execution_records
from agent.workflow.executor import AgentExecutor
from agent.workflow.planner import AgentPlanner
from core.llm_client import build_client
from core.models.feed import FeedGroup

logger = logging.getLogger(__name__)

class SummarizeAgenticWorkflow:
    def __init__(self, lazy_init: bool = False):
        """Initialize the agent workflow.
        
        Args:
            lazy_init: If True, defer AI client initialization until first use.
                      This allows the app to start without API keys configured.
        """
        self._client = None
        self._planner = None
        self._executor = None
        self.state_tracker = {}
        self.state = None
        
        if not lazy_init:
            self._init_client()
    
    def _init_client(self):
        """Initialize the AI client and pipeline components.
        
        Raises:
            APIKeyNotConfiguredError: If the API key is not configured.
        """
        if self._client is None:
            self._client = build_client()
            self._planner = AgentPlanner(self._client)
            self._executor = AgentExecutor(self._client)
    
    @property
    def planner(self) -> AgentPlanner:
        self._init_client()
        return self._planner
    
    @property
    def executor(self) -> AgentExecutor:
        self._init_client()
        return self._executor

    async def summarize(
        self,
        hour_gap: int,
        group_ids: Optional[list[int]],
        focus: str = "",
        on_step: Optional[StepCallback] = None,
    ):
        # This will raise APIKeyNotConfiguredError if API key is not set
        self._init_client()
        
        groups, articles = await get_recent_group_update(hour_gap, group_ids, focus)

        self.state = self._build_state(groups, articles, focus, on_step)
        log_step(
            self.state, f"🚀 Agent启动，获取到 {len(self.state['raw_articles'])} 篇文章"
        )

        log_step(self.state, "📋 开始规划阶段...")
        plan = await self.planner.plan(self.state)
        logger.info("Plan: %s", plan)

        log_step(self.state, "⚡ 开始执行阶段...")
        results = await self.executor.execute(self.state)
        logger.info("Results: %s", results)
        # 提取结果字符串和成功状态
        result_strings = [result for result, _ in results]
        success_statuses = [success for _, success in results]
        log_step(self.state, f"✅ Agent执行完成，共生成 {sum(success_statuses)} 篇")
        if not results:
            return "", []
        # 使用工具保存执行记录
        await save_current_execution_records(self.state)
        
        # 返回简报内容和外部搜索结果
        ext_info = self.state.get("ext_info", [])
        return "\n\n".join(result_strings), ext_info
        

    def _build_state(
        self,
        groups: list[FeedGroup],
        articles: list[RawArticle],
        focus: str = "",
        on_step: Optional[StepCallback] = None,
    ) -> AgentState:
        state = AgentState(
            groups=groups, raw_articles=articles, log_history=[], focus=focus
        )
        if on_step:
            state["on_step"] = on_step
        return state

    def get_log_history(self) -> list[str]:
        return self.state["log_history"]