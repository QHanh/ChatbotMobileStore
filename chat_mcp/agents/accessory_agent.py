"""AccessoryAgent: agent tư vấn/truy vấn phụ kiện.

Định hướng logic:
- Sử dụng ReAct loop (create_react_agent) để LLM tự quyết định gọi tool.
- Tool: accessories_search (MCP).
- Prompt đặc biệt: hướng dẫn trích xuất `cum_dac_trung` (Brand + Model).
"""

from typing import List

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .base import AgentContext, AgentResult, call_mcp_tool


class AccessoryAgent:
    agent_type: str = "accessory"

    def _select_tools(self, tenant_tools):
        tools_by_name = {
            getattr(t, "name", ""): t
            for t in tenant_tools
            if getattr(t, "name", None)
        }
        default_tools = []
        if "accessories_search" in tools_by_name:
            default_tools.append(tools_by_name["accessories_search"])
        extra_tools = [
            t
            for name, t in tools_by_name.items()
            if name != "accessories_search"
        ]
        return default_tools + extra_tools

    async def run(self, context: AgentContext) -> AgentResult:
        """Tư vấn/truy vấn phụ kiện cho tenant sử dụng ReAct/Tool Calling."""

        tenant_tools = context.tools or []
        if not tenant_tools:
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình công cụ tìm kiếm phụ kiện cho tenant này.",
                observations=["no_tools_configured"],
                used_tools=[],
            )

        tools = self._select_tools(tenant_tools)

        # Kiểm tra xem tool cần thiết có tồn tại không
        has_tool = any(getattr(t, "name", "") == "accessories_search" for t in tools)
        if not has_tool:
             return AgentResult(
                answer="Em chưa được gắn MCP tool 'accessories_search' nên chưa tra cứu được phụ kiện.",
                observations=["accessories_search_not_bound"],
                used_tools=[],
            )

        observations: List[str] = []
        llm = context.metadata.get("llm")
        if llm is None:
            observations.append("llm_not_provided")
            return AgentResult(
                answer="Hiện tại em chưa được cấu hình LLM cho agent phụ kiện.",
                observations=observations,
                used_tools=[],
            )

        # Lấy system prompt gốc từ context (nếu có) hoặc dùng default
        base_system_prompt = context.metadata.get("system_prompt", "")
        tenant_id = context.tenant_id
        thread_id = str(context.metadata.get("thread_id") or "")

        # Prompt ReAct chuyên biệt cho Accessory
        react_system_prompt = (
            "Bạn là chuyên gia tư vấn PHỤ KIỆN và LINH KIỆN sửa chữa điện thoại/laptop.\n"
            "Nhiệm vụ của bạn là trả lời câu hỏi của khách hàng bằng cách tìm kiếm thông tin chính xác.\n"
            "\n"
            "QUY TẮC QUAN TRỌNG VỀ CÔNG CỤ TÌM KIẾM (accessories_search):\n"
            "1. Tham số `query`: Nhập tên phụ kiện hoặc từ khóa tìm kiếm chung.\n"
            "2. Tham số `cum_dac_trung` (CỰC KỲ QUAN TRỌNG): \n"
            "   - Nếu câu hỏi chứa CỤM ĐẶC TRƯNG (Thương hiệu + Mã model/Ký hiệu số), bạn BẮT BUỘC phải trích xuất và truyền vào tham số này.\n"
            "   - Ví dụ: 'máy hàn quick 2008' -> cum_dac_trung='quick 2008'\n"
            "   - Ví dụ: 'kính hiển vi relife rl-m3t' -> cum_dac_trung='relife rl-m3t'\n"
            "   - Ví dụ: 'màn hình iphone 14 pro max' -> cum_dac_trung='iphone 14 pro max'\n"
            "   - Nếu không có cụm đặc trưng rõ ràng, hãy để trống tham số này.\n"
            "\n"
            "THÔNG SỐ KỸ THUẬT BẮT BUỘC KHI GỌI TOOL:\n"
            f"- Luôn truyền `customer_id` = '{tenant_id}' và `thread_id` = '{thread_id}' khi gọi tool `accessories_search`.\n"
            "- Không được sử dụng bất kỳ giá trị nào khác cho hai tham số này.\n"
            "\n"
            "QUY TRÌNH SUY LUẬN:\n"
            "1. Phân tích câu hỏi để xác định `query` và `cum_dac_trung`.\n"
            "2. Gọi tool `accessories_search` với các tham số đã trích xuất.\n"
            "3. Đọc kết quả trả về.\n"
            "4. Nếu kết quả tốt, tổng hợp câu trả lời thân thiện, ngắn gọn, gợi ý 2-3 sản phẩm tốt nhất.\n"
            "5. Nếu không có kết quả hoặc lỗi, hãy thử tìm kiếm lại với từ khóa rộng hơn hoặc thông báo khéo léo cho khách.\n"
            "\n"
            "Hãy trả lời bằng tiếng Việt, giọng điệu thân thiện, chuyên nghiệp."
        )

        full_system_prompt = react_system_prompt
        if base_system_prompt:
             full_system_prompt = f"{base_system_prompt}\n\n{react_system_prompt}"

        # Nếu có LLM, dùng create_agent (tương tự product_agent)
        print(f"[ACCESSORY] Context metadata keys: {list(context.metadata.keys())}")
        print(f"[ACCESSORY] LLM present: {llm is not None}")

        try:
            agent = create_agent(llm, tools)

            internal_messages: List[BaseMessage] = []
            internal_messages.append(SystemMessage(content=full_system_prompt))

            if context.history:
                internal_messages.extend(context.history)

            internal_messages.append(HumanMessage(content=context.user_input))

            result = await agent.ainvoke({"messages": internal_messages})

            # Parse result from LangGraph/LangChain agent
            raw_content = None
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, BaseMessage):
                        raw_content = last_msg.content
                    else:
                        raw_content = last_msg
            elif hasattr(result, "content"):
                raw_content = result.content
            else:
                raw_content = result

            answer_text = ""
            if isinstance(raw_content, str):
                answer_text = raw_content.strip()
            elif isinstance(raw_content, list):
                parts = []
                for item in raw_content:
                    if isinstance(item, dict):
                        text_val = item.get("text") or item.get("content")
                        if isinstance(text_val, str):
                            parts.append(text_val)
                            continue
                    parts.append(str(item))
                answer_text = "\n".join(parts).strip()
            else:
                answer_text = str(raw_content).strip()

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
            print(f"[ACCESSORY] create_agent failed: {e}")
            observations.append(f"accessory_agent_create_agent_error: {e}")
            # Fallback xuống logic thủ công nếu agent lỗi
            pass

        # Fallback: Logic thủ công (như cũ nhưng dùng constant)
        print("[ACCESSORY] Agent failed, falling back to manual tool call.")
        
        query_text = context.user_input
        
        args = {
            "customer_id": context.tenant_id,
            "thread_id": str(context.metadata.get("thread_id") or ""),
            "query": query_text,
            "offset": 0,
            "cum_dac_trung": None, 
        }

        raw = await call_mcp_tool(tools, "accessories_search", args)
        print(f"[ACCESSORY] Manual tool call result type: {type(raw)}")
        print(f"[ACCESSORY] Manual tool call result: {raw}")
        
        answer = ""
        # Xử lý trường hợp raw là object (ví dụ từ LangChain tool)
        if hasattr(raw, "content"):
             raw = getattr(raw, "content")
        
        if isinstance(raw, str):
             # Đôi khi tool trả về JSON string
             try:
                 import json
                 raw = json.loads(raw)
             except:
                 pass

        if isinstance(raw, dict) and "results" in raw:
             results = raw["results"]
             if results:
                 # Check if results is a list of strings or dicts
                 if isinstance(results[0], str):
                     answer = "\n\n".join(results)
                 else:
                     answer = "\n\n".join(str(r) for r in results)
             else:
                 answer = "Không tìm thấy phụ kiện phù hợp."
        elif isinstance(raw, dict) and "error" in raw:
            answer = f"Lỗi: {raw['error']}"
        elif isinstance(raw, list):
            answer = "\n\n".join(str(r) for r in raw)
        else:
            answer = str(raw)

        print(f"[ACCESSORY] Generated answer length: {len(answer)}")
        print(f"[ACCESSORY] Generated answer (first 100 chars): {answer[:100]}")

        return AgentResult(answer=answer, observations=observations, used_tools=["accessories_search"])
