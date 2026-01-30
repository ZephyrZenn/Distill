import logging
from typing import Optional
from agent.workflow import SummarizeAgenticWorkflow

logger = logging.getLogger(__name__)


# 单例实例
_agent_instance: Optional[SummarizeAgenticWorkflow] = None


def init_agent() -> SummarizeAgenticWorkflow:
    """应用启动时调用，初始化 Agent 单例。

    Uses lazy initialization so the app can start without API keys configured.
    API key errors will only occur when actually using the agent.
    """
    global _agent_instance
    if _agent_instance is None:
        # Use lazy_init=True to allow app to start without API key
        _agent_instance = SummarizeAgenticWorkflow(lazy_init=True)
        logger.info("Agent initialized (lazy mode - API key checked on first use)")
    return _agent_instance


def get_agent() -> SummarizeAgenticWorkflow:
    """获取 Agent 单例实例。

    Raises:
        RuntimeError: If agent is not initialized.
        APIKeyNotConfiguredError: When summarize() is called without API key configured.
    """
    if _agent_instance is None:
        raise RuntimeError("Agent 未初始化，请先调用 init_agent()")
    return _agent_instance
