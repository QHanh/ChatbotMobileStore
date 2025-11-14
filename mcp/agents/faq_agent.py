"""FAQAgent: agent xử lý câu hỏi thường gặp (FAQ).

Định hướng logic:
- Dùng MCP retrieval.search với index=faq để tìm câu hỏi tương tự.
- Có thể kết hợp với logic search_faqs hiện tại như adapter.
"""

from .base import AgentContext, AgentResult


class FAQAgent:
    agent_type: str = "faq"

    async def run(self, context: AgentContext) -> AgentResult:
        """Xử lý câu hỏi FAQ cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=faq).
        """
        # TODO: implement gọi MCP retrieval.search với index=faq.
        return AgentResult(answer="", observations=[], used_tools=[])
