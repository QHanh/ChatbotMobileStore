"""FAQAgent: agent xử lý câu hỏi thường gặp (FAQ).

Định hướng logic:
- Dùng MCP retrieval.search với index=faq để tìm câu hỏi tương tự.
- Có thể kết hợp với logic search_faqs hiện tại như adapter.
"""

from typing import List

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .base import AgentContext, AgentResult, call_mcp_tool


class FAQAgent:
    agent_type: str = "faq"

    def _select_tools(self, tenant_tools):
        tools_by_name = {
            getattr(t, "name", ""): t
            for t in tenant_tools
            if getattr(t, "name", None)
        }
        default_tools = []
        if "faq_search" in tools_by_name:
            default_tools.append(tools_by_name["faq_search"])
        extra_tools = [
            t
            for name, t in tools_by_name.items()
            if name != "faq_search"
        ]
        return default_tools + extra_tools

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý câu hỏi FAQ cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=faq).
        """

        tenant_tools = context.tools or []
        if not tenant_tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ FAQ cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tools = self._select_tools(tenant_tools)

        observations: List[str] = []

        llm = context.metadata.get("llm")
        if llm is None:
            observations.append("llm_not_provided")
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình LLM cho agent FAQ.",
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
            observations.append(f"faq_agent_create_agent_error: {e}")
            # Fallback xuống logic thủ công nếu agent lỗi

        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == "faq_search":
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'faq_search' nên chưa tra cứu được FAQ.",
                observations=["faq_search_not_bound"],
                used_tools=[],
            )

        args = {
            "customer_id": context.tenant_id,
            "query": context.user_input,
        }

        raw = await call_mcp_tool(tools, tool_name, args)
        answer = ""

        if isinstance(raw, dict):
            if "error" in raw:
                err = str(raw.get("error"))
                observations.append(err)
                answer = "Xin lỗi, em gặp lỗi khi tra cứu FAQ: " + err
            else:
                results = raw.get("results") or []
                if isinstance(results, list) and results:
                    top = results[0]
                    if isinstance(top, dict):
                        q = top.get("question") or ""
                        a = top.get("answer") or ""
                        answer = f"Câu hỏi tương tự: {q}\n\nTrả lời: {a}"
                    else:
                        answer = str(top)
                else:
                    answer = "Hiện tại em chưa tìm được câu hỏi thường gặp nào phù hợp."
        else:
            answer = str(raw) if raw is not None else "Hiện tại em chưa tìm được câu hỏi thường gặp nào phù hợp."

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
