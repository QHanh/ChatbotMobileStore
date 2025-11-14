"""StoreInfoAgent: agent lấy thông tin cửa hàng.

Giai đoạn đầu có thể wrap lại get_store_info_tool thành adapter.
"""

from .base import AgentContext, AgentResult


class StoreInfoAgent:
    agent_type: str = "store_info"

    async def run(self, context: AgentContext) -> AgentResult:
        """Lấy thông tin cửa hàng cho tenant.

        Skeleton:
        - Sau này: gọi MCP tool tương đương get_store_info_tool.
        """
        # TODO: implement adapter quanh get_store_info_tool hoặc MCP tool tương đương.
        return AgentResult(answer="", observations=[], used_tools=[])
