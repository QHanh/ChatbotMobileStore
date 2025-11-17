"""EscalationAgent: agent phụ trách chuyển tiếp cho người thật xử lý.

Giai đoạn đầu có thể wrap lại escalate_to_human_tool thành adapter.
"""

from typing import List

from .base import AgentContext, AgentResult, call_mcp_tool


class EscalationAgent:
    agent_type: str = "escalation"

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý escalations sang người thật.

        Skeleton:
        - Sau này: gọi MCP tool tương ứng escalate_to_human.
        """

        tools = context.tools or []
        if not tools:
            return AgentResult(
                answer="Em sẽ kết nối anh/chị với nhân viên tư vấn, nhưng hiện chưa có MCP escalation được cấu hình.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == "escalation_escalate_to_human":
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'escalation_escalate_to_human' nên chỉ có thể thông báo chuyển tiếp.",
                observations=["escalation_tool_not_bound"],
                used_tools=[],
            )

        raw = await call_mcp_tool(tools, tool_name, {})

        observations: List[str] = []
        if isinstance(raw, str):
            answer = raw
        else:
            answer = "Đang kết nối anh/chị với nhân viên tư vấn. Anh/chị vui lòng chờ trong giây lát..."

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
