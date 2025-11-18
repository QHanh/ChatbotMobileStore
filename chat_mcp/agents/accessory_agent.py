"""AccessoryAgent: agent tư vấn/truy vấn phụ kiện.

Định hướng logic:
- Thay thế search_accessories_tool bằng MCP tool retrieval.search (index=accessories),
  hỗ trợ đặc biệt cho tham số `cum_dac_trung`.
"""

from typing import Any, List

from langchain_core.messages import SystemMessage, HumanMessage

from .base import AgentContext, AgentResult, call_mcp_tool


class AccessoryAgent:
    agent_type: str = "accessory"

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn phụ kiện cho tenant.

        Skeleton:
        - Nhận context (tenant_id, user_input, history, bindings, defaults).
        - Sau này: dùng MCP retrieval.search (index=accessories) với xử lý cum_dac_trung.
        """

        tools = context.tools or []
        if not tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ tìm kiếm phụ kiện cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tool_name = None
        for t in tools:
            name = getattr(t, "name", None)
            if name == "accessories_search":
                tool_name = name
                break

        if tool_name is None:
            return AgentResult(
                answer="Em chưa được gắn MCP tool 'accessories_search' nên chưa tra cứu được phụ kiện.",
                observations=["accessories_search_not_bound"],
                used_tools=[],
            )

        # Lấy thread_id và query một cách robust, fallback từ metadata nếu cần.
        meta = context.metadata or {}
        thread_id = str(meta.get("thread_id") or "")

        query_text = context.user_input or meta.get("user_input") or ""

        args = {
            "customer_id": context.tenant_id,
            "thread_id": thread_id,
            "query": query_text,
            "offset": 0,
            "cum_dac_trung": None,
        }

        try:
            print(
                f"[ACCESSORY] meta={meta}, context.user_input={context.user_input!r}, "
                f"tool_args={args}"
            )
        except Exception:
            pass

        raw = await call_mcp_tool(tools, tool_name, args)

        observations: List[str] = []
        answer = ""

        llm = context.metadata.get("llm") if isinstance(context.metadata, dict) else None
        results: List[Any] = []

        if isinstance(raw, dict):
            if "error" in raw:
                err = str(raw.get("error"))
                observations.append(err)
                answer = "Xin lỗi, em gặp lỗi khi tìm phụ kiện: " + err
            else:
                results = raw.get("results") or []
                if isinstance(results, list) and results:
                    # Nếu có LLM từ orchestrator: dùng LLM để tổng hợp câu trả lời từ kết quả.
                    if llm is not None:
                        try:
                            numbered = []
                            for idx, r in enumerate(results, 1):
                                numbered.append(f"{idx}. {str(r)}")
                            results_text = "\n\n".join(numbered)

                            sys_msg = SystemMessage(
                                content=(
                                    "Bạn là trợ lý tư vấn PHỤ KIỆN. Dựa trên câu hỏi của khách và danh sách kết quả tìm kiếm "
                                    "(đã được hệ thống chuẩn hoá), hãy chọn những mục PHÙ HỢP NHẤT và trả lời rõ ràng, ngắn gọn, "
                                    "gợi ý 2-3 lựa chọn tốt nhất nếu có. Không liệt kê lại toàn bộ kết quả nếu quá dài, mà hãy tóm tắt "
                                    "những lựa chọn nổi bật nhất."
                                )
                            )
                            human_msg = HumanMessage(
                                content=(
                                    f"Câu hỏi của khách: {context.user_input}\n\n"
                                    f"Danh sách kết quả tìm kiếm phụ kiện (mỗi dòng là một gợi ý):\n{results_text}\n\n"
                                    "Hãy tư vấn cho khách, giải thích ngắn gọn và đề xuất những lựa chọn phù hợp nhất."
                                )
                            )

                            ainvoke = getattr(llm, "ainvoke", None)
                            if callable(ainvoke):
                                ai = await ainvoke([sys_msg, human_msg])
                            else:
                                ai = llm.invoke([sys_msg, human_msg])  # type: ignore[call-arg]

                            if hasattr(ai, "content"):
                                answer = str(ai.content)
                            else:
                                answer = str(ai)
                        except Exception as e:
                            observations.append(f"llm_summarize_error: {e}")
                            answer = "\n\n".join(str(r) for r in results)
                    else:
                        answer = "\n\n".join(str(r) for r in results)
                else:
                    answer = "Hiện tại em chưa tìm thấy phụ kiện phù hợp với yêu cầu của anh/chị."
        else:
            answer = str(raw) if raw is not None else "Hiện tại em chưa tìm thấy phụ kiện phù hợp với yêu cầu của anh/chị."

        try:
            preview = ""  # tránh in quá dài
            if isinstance(raw, dict):
                if "results" in raw and isinstance(raw["results"], list) and raw["results"]:
                    preview = str(raw["results"][0])[:200]
                elif "error" in raw:
                    preview = str(raw.get("error"))[:200]
            else:
                preview = str(raw)[:200]
            print(
                f"[ACCESSORY] raw_type={type(raw).__name__}, preview={preview!r}, "
                f"answer_len={len(answer) if isinstance(answer, str) else 'N/A'}"
            )
        except Exception:
            pass

        return AgentResult(answer=answer, observations=observations, used_tools=[tool_name])
