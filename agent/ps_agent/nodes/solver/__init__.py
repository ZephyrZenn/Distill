
from agent.ps_agent.nodes.solver.writer import DeepWriterNode
from agent.ps_agent.nodes.solver.tool_executor import ToolExecutorNode
from distill_lib.core.llm_client import LLMClient
from agent.ps_agent.state import PSAgentState
import logging
from .refiner import RefinerNode
logger = logging.getLogger(__name__)

_writer_node: DeepWriterNode | None = None
_tool_node: ToolExecutorNode | None = None
_refiner_node: RefinerNode | None = None


def set_solver_client(client: LLMClient) -> None:
    global _tool_node, _writer_node, _refiner_node
    _tool_node = ToolExecutorNode(client)
    _writer_node = DeepWriterNode(client)
    _refiner_node = RefinerNode(client)

async def writer_node(state: PSAgentState) -> dict:
    if _writer_node is None:  # pragma: no cover - defensive
        raise RuntimeError(
            "Writer client not initialized. Call set_solver_client first."
        )
    return await _writer_node(state)


async def tool_node(state: PSAgentState) -> dict:
    if _tool_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Tool client not initialized. Call set_solver_client first.")
    return await _tool_node(state)

async def refiner_node(state: PSAgentState) -> dict:
    if _refiner_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Refiner client not initialized. Call set_solver_client first.")
    return await _refiner_node(state)

__all__ = [
    "set_solver_client",
    "writer_node",
    "tool_node",
    "refiner_node",
]