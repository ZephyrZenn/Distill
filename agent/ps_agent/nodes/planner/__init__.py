from distill_lib.core.llm_client import LLMClient
from agent.ps_agent.nodes.planner.bootstrap import BootstrapNode
from agent.ps_agent.nodes.planner.researcher import ResearchPlannerNode
from agent.ps_agent.nodes.planner.structure import StructureNode
from agent.ps_agent.state import PSAgentState


_bootstrap_node: BootstrapNode | None = None
_research_planner_node: ResearchPlannerNode | None = None
_structure_node: StructureNode | None = None

def set_planner_client(client: LLMClient) -> None:
    """Register the shared AI client for this node."""
    global _bootstrap_node, _research_planner_node, _structure_node
    _bootstrap_node = BootstrapNode(client)
    _research_planner_node = ResearchPlannerNode(client)
    _structure_node = StructureNode(client)
    
async def structure_node(state: PSAgentState) -> dict:
    if _structure_node is None:
        raise RuntimeError("Structure client not initialized. Call set_planner_client first.")
    return await _structure_node(state)

async def bootstrap_node(state: PSAgentState) -> dict:
    """LangGraph entrypoint for the bootstrap node."""
    if _bootstrap_node is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "Planner client not initialized. Call set_planner_client first."
        )
    return await _bootstrap_node(state)


async def research_planner_node(state: PSAgentState) -> dict:
    if _research_planner_node is None:
        raise RuntimeError(
            "Research planner client not initialized. Call set_planner_client first."
        )
    return await _research_planner_node(state)

__all__ = [
    "structure_node",
    "research_planner_node",
    "bootstrap_node",
    "set_planner_client",
]