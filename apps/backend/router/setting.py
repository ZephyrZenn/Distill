from fastapi import APIRouter

from agent.ps_agent import check_ps_agent_requirements
from distill_lib.core.config.loader import get_config, get_api_key_env_var, is_api_key_configured

from apps.backend.models.common import success_with_data
from apps.backend.models.converters import request_to_model_config
from apps.backend.models.request import ModifySettingRequest
from apps.backend.models.view_model import (
    AgentCheckResponse,
    AgentCheckVO,
    SettingResponse,
)
from apps.backend.services import setting_service

router = APIRouter(prefix="/setting", tags=["setting"])


@router.get("/", response_model=SettingResponse)
async def get_setting():
    setting_vo = setting_service.get_setting()
    return success_with_data(setting_vo)


@router.get("/agent-check", response_model=AgentCheckResponse)
async def get_agent_config_check():
    """检查 Agent 模式所需配置是否齐全（LLM、Embedding、Tavily 等）。"""
    missing: list[str] = []
    # LLM API Key
    try:
        cfg = get_config()
        if not is_api_key_configured(cfg.model.provider):
            env_var = get_api_key_env_var(cfg.model.provider)
            missing.append(f"LLM API Key（需配置 {env_var}）")
    except Exception:
        missing.append("LLM 配置（请检查 config.toml 与对应 API Key 环境变量）")
    # PS Agent 依赖：Embedding、Tavily
    ok_agent, missing_agent = check_ps_agent_requirements()
    missing.extend(missing_agent)
    ready = len(missing) == 0
    return success_with_data(AgentCheckVO(ready=ready, missing=missing))


@router.post("/")
async def modify_setting(request: ModifySettingRequest):
    model_config = request_to_model_config(request.model) if request.model else None
    setting_service.update_setting(
        model=model_config,
        lightweight_model=request.lightweight_model,
        embedding=request.embedding,
        rate_limit=request.rate_limit,
        context=request.context,
        agent_limits=request.agent_limits,
    )
    return success_with_data(None)
