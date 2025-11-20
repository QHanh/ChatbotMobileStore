"""ServiceAgent: agent tư vấn/truy vấn dịch vụ sửa chữa.

Định hướng logic:
- Thay thế search_services_tool bằng MCP tool retrieval.search với index=services.
"""

from typing import List

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from chat_mcp.core.constants import TOOL_SERVICES_SEARCH
from .base import AgentContext, AgentResult, call_mcp_tool


class ServiceAgent:
    agent_type: str = "service"

    def _select_tools(self, tenant_tools):
        tools_by_name = {
            getattr(t, "name", ""): t
            for t in tenant_tools
            if getattr(t, "name", None)
        }
        default_tools = []
        if TOOL_SERVICES_SEARCH in tools_by_name:
            default_tools.append(tools_by_name[TOOL_SERVICES_SEARCH])
        extra_tools = [
            t
            for name, t in tools_by_name.items()
            if name != TOOL_SERVICES_SEARCH
        ]
        return default_tools + extra_tools

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn dịch vụ cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=services).
        """

        tenant_tools = context.tools or []
        if not tenant_tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ tìm kiếm dịch vụ cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tools = self._select_tools(tenant_tools)

        observations: List[str] = []

        llm = context.metadata.get("llm")
        if llm is None:
            observations.append("llm_not_provided")
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình LLM cho agent dịch vụ.",
                observations=observations,
                used_tools=[],
            )
        system_prompt = context.metadata.get("system_prompt", "")

        # Nếu có LLM, ưu tiên dùng ReAct agent với toàn bộ MCP tools của agent.
        try:
            agent = create_agent(llm, tools)

            internal_messages: List[BaseMessage] = []
            if system_prompt:
                internal_messages.append(SystemMessage(content=system_prompt))
            if context.history:
                internal_messages.extend(context.history)
            internal_messages.append(HumanMessage(content=context.user_input))

            result = await agent.ainvoke({"messages": internal_messages})

            answer_text = ""
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, BaseMessage):
                        answer_text = last_msg.content
                    else:
                        answer_text = str(last_msg)
            elif hasattr(result, "content"):
                answer_text = result.content
            else:
                answer_text = str(result)

            if isinstance(answer_text, str):
                answer_text = answer_text.strip()

            if answer_text:
                return AgentResult(
                    answer=answer_text,
                    observations=observations,
                    used_tools=[
                        getattr(t, "name", "")
                        for t in tools
                        if getattr(t, "name", None)
                    ],
                )
        except Exception as e:
            observations.append(f"service_agent_create_agent_error: {e}")
            # Fallback xuống logic thủ công nếu agent lỗi

        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == TOOL_SERVICES_SEARCH:
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'services_search' nên chưa tra cứu được dịch vụ.",
                observations=["services_search_not_bound", *observations],
                used_tools=[],
            )

        thread_id = str(context.metadata.get("thread_id", ""))

        args = {
            "customer_id": context.tenant_id,
            "thread_id": thread_id,
            "query": context.user_input,
            "offset": 0,
        }

        raw = await call_mcp_tool(tools, tool_name, args)
        answer = ""

        if isinstance(raw, dict):
            if "error" in raw:
                err = str(raw.get("error"))
                observations.append(err)
                answer = "Xin lỗi, em gặp lỗi khi tìm dịch vụ: " + err
            else:
                results = raw.get("results") or []
                if isinstance(results, list) and results:
                    answer = "\n\n".join(str(r) for r in results)
                else:
                    answer = "Hiện tại em chưa tìm thấy dịch vụ phù hợp với yêu cầu của anh/chị."
        else:
            answer = str(raw) if raw is not None else "Hiện tại em chưa tìm thấy dịch vụ phù hợp với yêu cầu của anh/chị."

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
