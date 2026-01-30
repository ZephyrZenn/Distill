"""Bootstrap node for the agentic daily-research workflow."""

from __future__ import annotations

import logging
import re

from core.llm_client import LLMClient
from core.models.llm import Message

from agent.utils import extract_json
from ..prompts import BOOTSTRAP_BUCKET_PROMPT, BOOTSTRAP_SYSTEM_PROMPT, build_bootstrap_user_prompt
from ..state import PSAgentState, log_step
from ..models import FocusBucket

logger = logging.getLogger(__name__)


class BootstrapNode:
    """Prepare the initial conversation and lightweight focus keywords."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        focus = state["focus"].strip()
        logger.info(
            "[bootstrap] run_id=%s focus=%s date=%s",
            state.get("run_id", "-"),
            focus,
            state["current_date"],
        )

        keywords = _heuristic_keywords(focus)
        logger.info(
            "[bootstrap] run_id=%s keywords=%s",
            state.get("run_id", "-"),
            ",".join(keywords[:8]),
        )

        # Generate Focus Buckets (P0 Feature)
        focus_buckets = []
        try:
            bucket_messages = [
                Message.system(BOOTSTRAP_BUCKET_PROMPT).set_priority(0),
                Message.user(f"Focus: {focus}").set_priority(0)
            ]
            response = await self.client.completion(bucket_messages)
            data = extract_json(response)
            for b in data.get("buckets", []):
                focus_buckets.append(FocusBucket(
                    id=str(b.get("id", "")).strip(),
                    name=str(b.get("name", "")).strip(),
                    description=str(b.get("description", "")).strip(),
                    reasoning=str(b.get("reasoning", "")).strip(),
                    status="EMPTY",
                    matched_items=[]
                ))
        except Exception as exc:
            logger.warning(f"[bootstrap] Failed to generate buckets: {exc}")

        messages = [
            Message.system(BOOTSTRAP_SYSTEM_PROMPT).set_priority(0),
            Message.user(
                build_bootstrap_user_prompt(focus=focus, current_date=state["current_date"])
            ).set_priority(0),
        ]

        return {
            **log_step(
                state,
                f"📋 bootstrap: focus='{focus}' keywords={len(keywords)} buckets={len(focus_buckets)}",
            ),

            "messages": messages,
            "focus_keywords": keywords,
            "focus_buckets": focus_buckets,
            "status": "researching",
            "last_error": None,
        }


def _heuristic_keywords(text: str, *, limit: int = 8) -> list[str]:
    """Extract simple keywords without another LLM call.

    We intentionally keep this deterministic and cheap.
    """
    tokens = re.split(r"[\s,，。.!！？;；:/\\|]+", text)
    clean = [t.strip() for t in tokens if len(t.strip()) >= 2]

    # Preserve order but deduplicate.
    seen: set[str] = set()
    keywords: list[str] = []
    for token in clean:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


# LangGraph wiring helpers ---------------------------------------------------

_bootstrap_node: BootstrapNode | None = None


def set_planner_client(client: LLMClient) -> None:
    """Register the shared AI client for this node."""
    global _bootstrap_node
    _bootstrap_node = BootstrapNode(client)


async def planner_node(state: PSAgentState) -> dict:
    """LangGraph entrypoint for the bootstrap node."""
    if _bootstrap_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Planner client not initialized. Call set_planner_client first.")
    return await _bootstrap_node(state)


__all__ = ["planner_node", "set_planner_client"]
