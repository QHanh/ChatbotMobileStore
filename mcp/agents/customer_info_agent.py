"""CustomerInfoAgent: agent kiểm tra / lấy thông tin khách hàng trong thread.

Giai đoạn đầu có thể wrap lại check_customer_info_tool thành adapter.
"""

from .base import AgentContext, AgentResult


class CustomerInfoAgent:
    agent_type: str = "customer_info"

    async def run(self, context: AgentContext) -> AgentResult:
        """Kiểm tra / lấy thông tin khách hàng cho tenant.

        Skeleton:
        - Sau này: gọi MCP tool tương đương check_customer_info_tool.
        """
        # TODO: implement adapter quanh check_customer_info_tool hoặc MCP tool tương đương.
        return AgentResult(answer="", observations=[], used_tools=[])
