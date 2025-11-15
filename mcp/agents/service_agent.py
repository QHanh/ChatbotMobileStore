"""ServiceAgent: agent tư vấn/truy vấn dịch vụ sửa chữa.

Định hướng logic:
- Thay thế search_services_tool bằng MCP tool retrieval.search với index=services.
"""

from typing import List

from .base import AgentContext, AgentResult, call_mcp_tool


class ServiceAgent:
    agent_type: str = "service"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn dịch vụ cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=services).
        """

        tools = context.tools or []
        if not tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ tìm kiếm dịch vụ cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == "services_search":
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'services_search' nên chưa tra cứu được dịch vụ.",
                observations=["services_search_not_bound"],
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

        observations: List[str] = []
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
