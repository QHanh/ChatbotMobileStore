"""KnowledgeAgent: agent truy vấn tri thức tổng quát bằng GraphRAG / vector.

Định hướng logic:
- Dùng MCP retrieval.graphrag hoặc vector_search để truy vấn tri thức cửa hàng.
- Tương đương graphrag_search_tool hiện tại.
"""

from .base import AgentContext, AgentResult


class KnowledgeAgent:
    agent_type: str = "knowledge"

    async def run(self, context: AgentContext) -> AgentResult:
        """Truy vấn tri thức (GraphRAG / vector) cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.graphrag.
        """
        # TODO: implement gọi MCP retrieval.graphrag.
        return AgentResult(answer="", observations=[], used_tools=[])
