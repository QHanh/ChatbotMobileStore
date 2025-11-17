"""VisionAgent: agent phụ trách xử lý input là ảnh.

Trong kiến trúc MCP:
- Sẽ gọi tool `vision.identify_product` từ MCP server "vision" thông qua langchain-mcp-adapters.
- Skeleton hiện tại chỉ định nghĩa interface, chưa gọi MCP thực tế.
"""

from typing import Any, List

from langchain_core.messages import BaseMessage

from .base import AgentContext, AgentResult


class VisionAgent:
    agent_type: str = "vision"

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý truy vấn có ảnh, sử dụng MCP tool vision.identify_product (sau này).

        Giai đoạn skeleton:
        - Tận dụng context.user_input + history.
        - Sau này sẽ được nối với MCP tools (vision.identify_product) qua orchestrator.
        """
        # TODO: implement gọi MCP tool vision.identify_product.
        return AgentResult(answer="", observations=[], used_tools=[])
