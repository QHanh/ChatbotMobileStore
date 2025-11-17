"""OrderAgent: agent phụ trách tạo đơn hàng (sản phẩm/dịch vụ/phụ kiện).

Giai đoạn đầu có thể wrap lại create_order_*_tool thành adapter.
"""

from .base import AgentContext, AgentResult


class OrderAgent:
    agent_type: str = "order"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tạo đơn hàng dựa trên ngữ cảnh hiện tại.

        Skeleton:
        - Sau này: gọi MCP tool tương ứng (create_order_product/service/accessory).
        """
        # TODO: implement adapter quanh create_order_*_tool hoặc MCP tool tương đương.
        return AgentResult(answer="", observations=[], used_tools=[])
