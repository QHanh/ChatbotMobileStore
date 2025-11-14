"""AccessoryAgent: agent tư vấn/truy vấn phụ kiện.

Định hướng logic:
- Thay thế search_accessories_tool bằng MCP tool retrieval.search (index=accessories),
  hỗ trợ đặc biệt cho tham số `cum_dac_trung`.
"""

from .base import AgentContext, AgentResult


class AccessoryAgent:
    agent_type: str = "accessory"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn phụ kiện cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=accessories) với xử lý cum_dac_trung.
        """
        # TODO: implement gọi MCP retrieval.search với index=accessories.
        return AgentResult(answer="", observations=[], used_tools=[])
