from agent.ps_agent.nodes.evaluator.material_curation import MaterialCurationNode
from agent.ps_agent.nodes.evaluator.plan_reviewer import PlanReviewerNode
from agent.ps_agent.nodes.evaluator.summary_reviewer import SummaryReviewerNode
from distill_lib.core.llm_client import LLMClient
from agent.ps_agent.state import PSAgentState

_material_curation_node: MaterialCurationNode | None = None
_plan_reviewer_node: PlanReviewerNode | None = None
_summary_reviewer_node: SummaryReviewerNode | None = None


def set_evaluator_client(client: LLMClient, audit_client: LLMClient) -> None:
    global _material_curation_node, _plan_reviewer_node, _summary_reviewer_node
    _material_curation_node = MaterialCurationNode(client, audit_client)
    _plan_reviewer_node = PlanReviewerNode(client)
    _summary_reviewer_node = SummaryReviewerNode(client)


async def material_curation_node(state: PSAgentState) -> dict:
    if _material_curation_node is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "Material curation client not initialized. Call set_material_curation_client first."
        )
    return await _material_curation_node(state)


async def plan_reviewer_node(state: PSAgentState) -> dict:
    if _plan_reviewer_node is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "Plan reviewer client not initialized. Call set_plan_reviewer_client first."
        )
    return await _plan_reviewer_node(state)

async def summary_reviewer_node(state: PSAgentState) -> dict:
    if _summary_reviewer_node is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "Summary reviewer client not initialized. Call set_summary_reviewer_client first."
        )
    return await _summary_reviewer_node(state)

__all__ = [
    "material_curation_node",
    "set_evaluator_client",
    "plan_reviewer_node",
    "summary_reviewer_node",
]
