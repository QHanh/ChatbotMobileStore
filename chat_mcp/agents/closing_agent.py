"""ClosingAgent: agent phụ trách kết thúc hội thoại."""

from .base import AgentContext, AgentResult


class ClosingAgent:
    agent_type: str = "closing"

    async def run(self, context: AgentContext) -> AgentResult:
        """Kết thúc hội thoại một cách tự nhiên, lịch sự.

        Skeleton:
        - Sau này: gọi MCP tool tương ứng end_conversation.
        """
        # TODO: implement adapter quanh end_conversation_tool hoặc MCP tool tương đương.
        return AgentResult(answer="", observations=[], used_tools=[])
