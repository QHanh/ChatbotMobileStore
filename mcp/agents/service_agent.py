"""ServiceAgent: agent tư vấn/truy vấn dịch vụ sửa chữa.

Định hướng logic:
- Thay thế search_services_tool bằng MCP tool retrieval.search với index=services.
"""

from .base import AgentContext, AgentResult


class ServiceAgent:
    agent_type: str = "service"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn dịch vụ cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=services).
        """
        # TODO: implement gọi MCP retrieval.search với index=services.
        return AgentResult(answer="", observations=[], used_tools=[])
