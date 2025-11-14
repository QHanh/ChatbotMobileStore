"""EscalationAgent: agent phụ trách chuyển tiếp cho người thật xử lý.

Giai đoạn đầu có thể wrap lại escalate_to_human_tool thành adapter.
"""

from .base import AgentContext, AgentResult


class EscalationAgent:
    agent_type: str = "escalation"

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý escalations sang người thật.

        Skeleton:
        - Sau này: gọi MCP tool tương ứng escalate_to_human.
        """
        # TODO: implement adapter quanh escalate_to_human_tool hoặc MCP tool tương đương.
        return AgentResult(answer="", observations=[], used_tools=[])
