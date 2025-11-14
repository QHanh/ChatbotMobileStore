"""ProductAgent: agent tư vấn/truy vấn sản phẩm.

Định hướng logic:
- Thay thế các tool search_products_tool hiện tại bằng MCP tool retrieval.search / vector_search / graphrag
  với index=products.
- Giai đoạn đầu có thể sử dụng MCP retrieval.search, hoặc adapter bọc quanh search_products_logic.
"""

from .base import AgentContext, AgentResult


class ProductAgent:
    agent_type: str = "product"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn sản phẩm cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: chọn tool MCP tương ứng từ bindings (retrieval.search, vector_search, graphrag).
        - Gọi tool và tổng hợp kết quả thành answer.
        """
        # TODO: implement gọi MCP retrieval.search / vector_search / graphrag với index=products.
        return AgentResult(answer="", observations=[], used_tools=[])
