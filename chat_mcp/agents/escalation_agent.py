"""EscalationAgent: agent phụ trách chuyển tiếp cho người thật xử lý.

Giai đoạn đầu có thể wrap lại escalate_to_human_tool thành adapter.
"""

from typing import List

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .base import AgentContext, AgentResult, call_mcp_tool


class EscalationAgent:
    agent_type: str = "escalation"

    def _select_tools(self, tenant_tools):
        tools_by_name = {
            getattr(t, "name", ""): t
            for t in tenant_tools
            if getattr(t, "name", None)
        }
        default_tools = []
        if "escalation_escalate_to_human" in tools_by_name:
            default_tools.append(tools_by_name["escalation_escalate_to_human"])
        extra_tools = [
            t
            for name, t in tools_by_name.items()
            if name != "escalation_escalate_to_human"
        ]
        return default_tools + extra_tools

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý escalations sang người thật.

        Skeleton:
        - Sau này: gọi MCP tool tương ứng escalate_to_human.
        """

        tenant_tools = context.tools or []
        if not tenant_tools:
            return AgentResult(
                answer="Em sẽ kết nối anh/chị với nhân viên tư vấn, nhưng hiện chưa có MCP escalation được cấu hình.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tools = self._select_tools(tenant_tools)

        observations: List[str] = []

        llm = context.metadata.get("llm")
        if llm is None:
            observations.append("llm_not_provided")
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình LLM cho agent escalation.",
                observations=observations,
                used_tools=[],
            )
        system_prompt = context.metadata.get("system_prompt", "")

        # Nếu có LLM, ưu tiên dùng ReAct agent với toàn bộ MCP tools của agent.
        try:
            agent = create_agent(llm, tools)

            internal_messages: List[BaseMessage] = []
            if system_prompt:
                internal_messages.append(SystemMessage(content=system_prompt))
            if context.history:
                internal_messages.extend(context.history)
            internal_messages.append(HumanMessage(content=context.user_input))

            result = await agent.ainvoke({"messages": internal_messages})

            answer_text = ""
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, BaseMessage):
                        answer_text = last_msg.content
                    else:
                        answer_text = str(last_msg)
            elif hasattr(result, "content"):
                answer_text = result.content
            else:
                answer_text = str(result)

            if isinstance(answer_text, str):
                answer_text = answer_text.strip()

            if answer_text:
                return AgentResult(
                    answer=answer_text,
                    observations=observations,
                    used_tools=[
                        getattr(t, "name", "")
                        for t in tools
                        if getattr(t, "name", None)
                    ],
                )
        except Exception as e:
            observations.append(f"escalation_agent_create_agent_error: {e}")
            # Fallback xuống logic thủ công nếu agent lỗi

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
        if isinstance(raw, str):
            answer = raw
        else:
            answer = "Đang kết nối anh/chị với nhân viên tư vấn. Anh/chị vui lòng chờ trong giây lát..."

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
