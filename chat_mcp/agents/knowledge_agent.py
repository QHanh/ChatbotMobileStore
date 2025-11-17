"""KnowledgeAgent: agent truy vấn tri thức tổng quát bằng GraphRAG / vector.

Định hướng logic:
- Dùng MCP retrieval.graphrag hoặc vector_search để truy vấn tri thức cửa hàng.
- Tương đương graphrag_search_tool hiện tại.
"""

from typing import List

from .base import AgentContext, AgentResult, call_mcp_tool


class KnowledgeAgent:
    agent_type: str = "knowledge"

    async def run(self, context: AgentContext) -> AgentResult:
        """Truy vấn tri thức (GraphRAG / vector) cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.graphrag.
        """

        tools = context.tools or []
        if not tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ tra cứu tri thức cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == "knowledge_graphrag":
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'knowledge_graphrag' nên chưa tra cứu được tri thức.",
                observations=["knowledge_graphrag_not_bound"],
                used_tools=[],
            )

        args = {
            "customer_id": context.tenant_id,
            "mode": "basic",
            "query": context.user_input,
            "community_level": None,
            "response_type": None,
        }

        raw = await call_mcp_tool(tools, tool_name, args)

        observations: List[str] = []
        answer = ""

        if isinstance(raw, dict):
            if "error" in raw:
                err = str(raw.get("error"))
                observations.append(err)
                answer = "Xin lỗi, em gặp lỗi khi truy vấn tri thức: " + err
            else:
                answer = str(raw.get("answer") or "").strip()
                if not answer:
                    answer = "Hiện tại em chưa tìm được thông tin phù hợp trong kho tri thức."
        else:
            answer = str(raw) if raw is not None else "Hiện tại em chưa tìm được thông tin phù hợp trong kho tri thức."

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
