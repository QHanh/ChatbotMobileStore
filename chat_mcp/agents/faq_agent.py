"""FAQAgent: agent xử lý câu hỏi thường gặp (FAQ).

Định hướng logic:
- Dùng MCP retrieval.search với index=faq để tìm câu hỏi tương tự.
- Có thể kết hợp với logic search_faqs hiện tại như adapter.
"""

from typing import List

from .base import AgentContext, AgentResult, call_mcp_tool


class FAQAgent:
    agent_type: str = "faq"

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý câu hỏi FAQ cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=faq).
        """

        tools = context.tools or []
        if not tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ FAQ cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

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

        observations: List[str] = []
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
