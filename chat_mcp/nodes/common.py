from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from chat_mcp.states import ChatState


def get_messages_from_state(state: ChatState) -> List[BaseMessage]:
    """Lấy danh sách messages từ state hoặc từ state['input']['messages'].

    Luôn trả về list[BaseMessage] (có thể rỗng) để tránh lỗi None.
    """

    messages = state.get("messages")
    if messages is None:
        inner = state.get("input")  # type: ignore[assignment]
        if isinstance(inner, dict):
            messages = inner.get("messages")
    if messages is None:
        return []
    if not isinstance(messages, list):
        from langchain_core.messages import BaseMessage as _BM  # tránh import vòng

        if isinstance(messages, _BM):
            return [messages]
        return []
    return messages


def get_context_from_state(state: ChatState) -> Dict[str, Any]:
    """Lấy context từ state hoặc từ state['input']['context'] nếu có.

    Luôn trả về dict (có thể rỗng) để tránh lỗi None.
    """

    context = state.get("context")
    if context is None:
        inner = state.get("input")  # type: ignore[assignment]
        if isinstance(inner, dict):
            context = inner.get("context")
    if not isinstance(context, dict):
        return {}
    return context


def resolve_user_input(state: ChatState, config: RunnableConfig) -> str:
    """Chuẩn hoá cách lấy user_input từ state + config.

    Ưu tiên:
    1. HumanMessage cuối cùng trong messages (nếu content là str).
    2. Các key tường minh trong config/state/context:
       - config['configurable']['user_input']
       - state['user_input']
       - state['input']['user_input'] (nếu LangGraph bọc state)
       - context['raw_user_input']
       - context['metadata']['user_input']
    Luôn trả về string (có thể rỗng) để tránh lỗi None.
    """

    messages = get_messages_from_state(state)
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, HumanMessage) and isinstance(getattr(last_msg, "content", None), str):
            raw = (last_msg.content or "").strip()
            if raw:
                return raw

    configurable: Dict[str, Any] = {}
    try:
        configurable = (config or {}).get("configurable") or {}
    except Exception:
        configurable = {}

    raw_ui: Any = configurable.get("user_input")
    if not isinstance(raw_ui, str) or not raw_ui.strip():
        raw_ui = state.get("user_input")
    if not isinstance(raw_ui, str) or not raw_ui.strip():
        inner = state.get("input")  # type: ignore[assignment]
        if isinstance(inner, dict):
            candidate = inner.get("user_input")
            if isinstance(candidate, str) and candidate.strip():
                raw_ui = candidate
    ctx = get_context_from_state(state)
    if (not isinstance(raw_ui, str)) or (not raw_ui.strip()):
        candidate = ctx.get("raw_user_input")
        if isinstance(candidate, str) and candidate.strip():
            raw_ui = candidate
    if (not isinstance(raw_ui, str)) or (not raw_ui.strip()):
        meta = ctx.get("metadata") or {}
        if isinstance(meta, dict):
            candidate = meta.get("user_input")
            if isinstance(candidate, str) and candidate.strip():
                raw_ui = candidate

    if isinstance(raw_ui, str):
        return raw_ui.strip()
    return ""
