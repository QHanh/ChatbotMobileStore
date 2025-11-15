"""ProductAgent: agent tư vấn/truy vấn sản phẩm.

Định hướng logic:
- Thay thế các tool search_products_tool hiện tại bằng MCP tool retrieval.search / vector_search / graphrag
  với index=products.
- Giai đoạn đầu có thể sử dụng MCP retrieval.search, hoặc adapter bọc quanh search_products_logic.
"""

from typing import List

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .base import AgentContext, AgentResult, call_mcp_tool


class ProductAgent:
    agent_type: str = "product"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn sản phẩm cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: chọn tool MCP tương ứng từ bindings (retrieval.search, vector_search, graphrag).
        - Gọi tool và tổng hợp kết quả thành answer.
        """

        tools = context.tools or []
        if not tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ tìm kiếm sản phẩm cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        observations: List[str] = []

        llm = context.metadata.get("llm")
        system_prompt = context.metadata.get("system_prompt", "")

        # Ưu tiên dùng create_agent của LangChain với toàn bộ MCP tools được bind cho ProductAgent.
        # Điều này cho phép LLM tự quyết định cách gọi tool, giống ví dụ MCP trong docs.
        if llm is not None:
            try:
                agent = create_agent(llm, tools)

                internal_messages: List[BaseMessage] = []
                if system_prompt:
                    internal_messages.append(SystemMessage(content=system_prompt))
                if context.history:
                    internal_messages.extend(context.history)
                internal_messages.append(HumanMessage(content=context.user_input))

                result = await agent.ainvoke({"messages": internal_messages})

                content = getattr(result, "content", result)
                answer_text = content if isinstance(content, str) else str(content)
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
            except Exception as e:  # pragma: no cover - phòng thủ
                observations.append(f"product_agent_create_agent_error: {e}")

        # Fallback: gọi trực tiếp MCP tool products_search như trước.
        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == "products_search":
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'products_search' nên chưa tra cứu được sản phẩm.",
                observations=["products_search_not_bound", *observations],
                used_tools=[],
            )

        thread_id = str(context.metadata.get("thread_id", ""))

        args = {
            "customer_id": context.tenant_id,
            "thread_id": thread_id,
            "query": context.user_input,
            "offset": 0,
        }

        raw = await call_mcp_tool(tools, tool_name, args)

        answer = ""

        if isinstance(raw, dict):
            if "error" in raw:
                err = str(raw.get("error"))
                observations.append(err)
                answer = "Xin lỗi, em gặp lỗi khi tìm sản phẩm: " + err
            else:
                results = raw.get("results") or []
                if isinstance(results, list) and results:
                    answer = "\n\n".join(str(r) for r in results)
                else:
                    answer = "Hiện tại em chưa tìm thấy sản phẩm phù hợp với yêu cầu của anh/chị."
        else:
            answer = str(raw) if raw is not None else "Hiện tại em chưa tìm thấy sản phẩm phù hợp với yêu cầu của anh/chị."

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
