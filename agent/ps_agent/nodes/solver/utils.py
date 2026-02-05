from agent.ps_agent.state import PSAgentState

def _last_tool_calls(state: PSAgentState):
    for message in reversed(state.get("messages", [])):
        if message.role == "assistant" and message.tool_calls:
            return message.tool_calls
        if message.role == "assistant":
            return []
    return []

def _last_assistant_content(state: PSAgentState):
    for message in reversed(state.get("messages", [])):
        if message.role == "assistant":
            return message.content or ""
    return ""

__all__ = [
    "_last_tool_calls",
    "_last_assistant_content",
]