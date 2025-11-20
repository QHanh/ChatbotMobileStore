from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig

from chat_mcp.states import ChatState
from chat_mcp.agents.base import AgentContext, AgentResult
from chat_mcp.agents.service_agent import ServiceAgent

from .common import get_messages_from_state, get_context_from_state, resolve_user_input


def make_service_agent_node(tenant_id: str, tools_for_agent: List[Any]):
    async def node(state: ChatState, config: RunnableConfig) -> ChatState:
        agent_type = "service"

        try:
            print(
                f"[ORCH-AGENT] entry state keys for agent_type={agent_type!r}: "
                f"{list(state.keys())}"
            )
        except Exception:
            pass

        configurable: Dict[str, Any] = {}
        try:
            configurable = (config or {}).get("configurable") or {}
        except Exception:
            configurable = {}

        messages = list(get_messages_from_state(state))
        context = get_context_from_state(state)
        agent_prompts_ctx = context.get("agent_prompts", {})
        system_prompt = agent_prompts_ctx.get(agent_type, "")

        history_messages: List[BaseMessage] = messages[:-1] if messages else []
        user_input = resolve_user_input(state, config)

        try:
            print(
                f"[ORCH-AGENT] agent_type={agent_type!r} resolved user_input={user_input!r}, "
                f"state_user_input={state.get('user_input')!r}"
            )
        except Exception:
            pass

        metadata: Dict[str, Any] = {}
        raw_meta = context.get("metadata") or {}
        if isinstance(raw_meta, dict):
            metadata.update(raw_meta)
        thread_id = context.get("thread_id")
        if not thread_id:
            thread_id = state.get("thread_id")  # type: ignore[assignment]
        if not thread_id:
            inner = state.get("input")  # type: ignore[assignment]
            if isinstance(inner, dict):
                thread_id = inner.get("thread_id")  # type: ignore[assignment]
        if not thread_id:
            thread_id = configurable.get("thread_id")
        if thread_id:
            metadata.setdefault("thread_id", thread_id)
        llm_obj = context.get("llm")
        if llm_obj is not None:
            metadata.setdefault("llm", llm_obj)
        if system_prompt:
            metadata.setdefault("system_prompt", system_prompt)
        metadata.setdefault("tenant_id", tenant_id)

        chat_state: Dict[str, Any] = {}
        try:
            if tenant_id:
                chat_state["tenant_id"] = tenant_id
            if thread_id:
                chat_state["session_id"] = str(thread_id)
            if user_input:
                chat_state["user_message"] = user_input
            if messages:
                simple_messages: List[Dict[str, Any]] = []
                for m in messages:
                    content = getattr(m, "content", None)
                    if not isinstance(content, str):
                        continue
                    role = type(m).__name__.replace("Message", "").lower()
                    simple_messages.append({"role": role, "content": content})
                if simple_messages:
                    chat_state["messages"] = simple_messages
        except Exception:
            chat_state = {}

        if chat_state and "chat_state" not in metadata:
            metadata["chat_state"] = chat_state

        if "user_input" not in metadata and user_input:
            metadata["user_input"] = user_input

        try:
            print(
                f"[ORCH-AGENT] agent_type={agent_type!r} metadata.thread_id={metadata.get('thread_id')!r}, "
                f"state_thread_id={state.get('thread_id')!r}, context_thread_id={context.get('thread_id')!r}"
            )
        except Exception:
            pass

        agent_context = AgentContext(
            tenant_id=tenant_id,
            user_input=user_input,
            history=history_messages,
            bindings=None,
            defaults={},
            access=state.get("access"),
            tools=tools_for_agent,
            metadata=metadata,
        )

        try:
            agent = ServiceAgent()
            result: AgentResult = await agent.run(agent_context)  # type: ignore[call-arg]
        except Exception as e:
            print(f"[ORCH-AGENT] Error in service node: {e}")
            error: Dict[str, Any] = {
                "code": "service_agent_error",
                "message": str(e),
                "detail": repr(e),
            }
            return {"error": error}

        new_messages = list(messages)
        if result.answer:
            print(
                f"[ORCH-AGENT] Appending AIMessage with answer len={len(result.answer)}"
            )
            new_messages.append(AIMessage(content=result.answer))
        else:
            print("[ORCH-AGENT] result.answer is empty, NOT appending AIMessage")

        print(f"[ORCH-AGENT] Returning new_messages len={len(new_messages)}")
        return {
            "messages": new_messages,
        }

    return node
