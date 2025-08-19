import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain.chat_models import init_chat_model
import getpass
from functools import partial

load_dotenv()

from service.utils.tools import create_customer_tools
from database.database import Customer

def create_agent_executor(
    customer_id: str,
    customer_config: Customer,
    llm_provider: str = "google_genai",
    api_key: str = None
):
    """
    Tạo và trả về một Agent Executor, được cấu hình cho một khách hàng cụ thể.
    """
    if not api_key:
        raise ValueError("Bạn chưa thêm API key bên trang cấu hình.")

    if llm_provider == "google_genai":
        llm = init_chat_model(model="gemini-2.0-flash", model_provider="google_genai", api_key=api_key)
    elif llm_provider == "openai":
        llm = init_chat_model(model="gpt-4o-mini", model_provider="openai", api_key=api_key)
    else:
        raise ValueError(f"Không tìm thấy LLM provider: {llm_provider}")

    # Lấy thông tin cấu hình trực tiếp từ object Customer
    persona = {"ai_name": customer_config.ai_name, "ai_role": customer_config.ai_role}
    custom_prompt_text = customer_config.custom_prompt or ""
    service_feature_enabled = customer_config.service_feature_enabled
    accessory_feature_enabled = customer_config.accessory_feature_enabled

    customer_tools = create_customer_tools(customer_id, service_feature_enabled, accessory_feature_enabled)

    identity = ""
    if persona['ai_role']:
        identity = f"đóng vai một {persona['ai_role']} am hiểu và thân thiện"
    if persona['ai_name']:
        identity += f" tên là {persona['ai_name']}"

    # 1. Hướng dẫn cơ bản
    base_instructions = f"""
    Bạn là một chuyên gia tư vấn của một cửa hàng điện thoại, {identity}.
    Nhiệm vụ của bạn là tra cứu thông tin sản phẩm, dịch vụ và linh kiện **CHỈ** từ kho dữ liệu của cửa hàng bằng các công cụ được cung cấp.

    **QUY TẮC TỐI THƯỢNG (TUYỆT ĐỐI TUÂN THỦ):**
    1.  **BẠN KHÔNG CÓ KIẾN THỨC RIÊNG.** Toàn bộ kiến thức của bạn về sản phẩm, dịch vụ, linh kiện và tồn kho đều đến từ công cụ.
    2.  **LUÔN DÙNG CÔNG CỤ.** Với **MỌI** câu hỏi của khách hàng liên quan đến một sản phẩm, dịch vụ hoặc linh kiện (ví dụ: "iPhone 16", "thay pin", "ốp lưng"), bạn phải **NGAY LẬP TỨC** sử dụng công cụ tìm kiếm.
    3.  **KHÔNG GIẢ ĐỊNH.** Kể cả khi một sản phẩm nghe có vẻ không có thật hay chưa ra mắt, bạn vẫn phải dùng công cụ để kiểm tra. Nếu công cụ không tìm thấy gì, nghĩa là cửa hàng không có sản phẩm đó.
    4.  **KHÔNG TIẾT LỘ VAI TRÒ.** Nghiêm cấm tuyệt đối tiết lộ bạn là AI hay bot.
    5.  **LUÔN GIỮ THÁI ĐỘ LỄ PHÉP, TỰ NHIÊN VÀ THÂN THIỆN.** Luôn xưng hô khách hàng bằng "anh/chị" và "dạ" khi trả lời.
    """

    # 2. Hướng dẫn quy trình làm việc
    workflow_instructions_parts = []
    product_workflow = """-   Khi khách hỏi về **sản phẩm** (điện thoại, máy tính bảng, ...), dùng `search_products_tool`. Nếu khách chốt mua, dùng `create_order_product_tool`."""
    service_workflow = """-   Khi khách hỏi về **dịch vụ** (sửa chữa, thay pin, ...), dùng `search_services_tool`. Nếu khách chốt, dùng `create_order_service_tool`."""
    accessory_workflow = """-   Khi khách hỏi về **linh kiện / phụ kiện** (ốp lưng, sạc, tai nghe, ...), dùng `search_accessories_tool`. Nếu khách chốt mua, dùng `create_order_accessory_tool`."""

    workflow_steps = []
    if True: # Product is always enabled
        workflow_steps.append(product_workflow)
    if service_feature_enabled:
        workflow_steps.append(service_workflow)
    if accessory_feature_enabled:
        workflow_steps.append(accessory_workflow)

    workflow_instructions = f"""
**Quy trình làm việc:**
1.  Xác định nhu cầu của khách: **sản phẩm**, **dịch vụ**, hay **linh kiện/phụ kiện**.
2.  Sử dụng công cụ tìm kiếm tương ứng:
    {'\n   '.join(workflow_steps)}
3.  **Xử lý kết quả:**
    -   Nếu công cụ trả về danh sách rỗng (`[]`), thông báo cho khách là mặt hàng đó hiện **không có tại cửa hàng** và hỏi xem họ có muốn tham khảo lựa chọn khác không.
        -   Ví dụ sản phẩm: "Dạ em rất tiếc, bên em hiện không có iPhone 16 ạ. Anh/chị có muốn tham khảo dòng iPhone nào khác không ạ?"
        -   Ví dụ dịch vụ: "Dạ rất tiếc, bên em chưa có dịch vụ thay màn hình cho dòng máy này ạ."
        -   Ví dụ linh kiện: "Dạ em rất tiếc, bên em hiện đã hết hàng mẫu ốp lưng này rồi ạ."
    -   Nếu có kết quả, trình bày thông tin cho khách.
    -   Chỉ trình bày trước các thông tin chính. Các chi tiết khác như màu sắc, dung lượng, ... chỉ cung cấp khi khách hàng hỏi.
4.  Khi khách chốt đơn, sử dụng công cụ tạo đơn hàng tương ứng đã nêu ở bước 2.
    """
    
    other_instructions = """
    **Các tình huống khác:**
        - **Khách hàng phàn nàn/tức giận:** Hãy xin lỗi và sử dụng `escalate_to_human_tool`.
        - **Kết thúc trò chuyện:** Khi khách hàng không còn nhu cầu, hãy sử dụng `end_conversation_tool`.
    """

    final_system_prompt = "\n".join([
        base_instructions,
        workflow_instructions,
        custom_prompt_text,
        other_instructions
    ])

    prompt = ChatPromptTemplate.from_messages([
        ("system", final_system_prompt),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, customer_tools, prompt)

    agent_executor = AgentExecutor(
        agent=agent, 
        tools=customer_tools, 
        verbose=True,
        handle_parsing_errors=True
    )
    
    return agent_executor

def get_session_history(session_id: str, memory: dict):
    if session_id not in memory:
        memory[session_id] = []
    return memory[session_id]

async def invoke_agent_with_memory(agent_executor, session_id: str, user_input: str, memory: dict):
    """
    Gọi agent với input của người dùng và quản lý lịch sử trò chuyện.
    """
    chat_history = get_session_history(session_id, memory)
    
    response = await agent_executor.ainvoke({
        "input": user_input,
        "chat_history": chat_history
    })
    
    chat_history.extend([
        HumanMessage(content=user_input),
        AIMessage(content=response["output"]),
    ])
    
    return response

if __name__ == '__main__':
    import asyncio

    async def main():
        print("Đang khởi tạo agent...")
        # Phần này cần được cập nhật để giả lập object Customer cho việc test
        mock_customer_config = Customer(
            customer_id="test_customer",
            ai_name="TestBot",
            ai_role="trợ lý ảo test",
            custom_prompt="Luôn trả lời bằng tiếng Việt.",
            service_feature_enabled=True,
            accessory_feature_enabled=False
        )
        agent_executor = create_agent_executor(
            customer_id="test_customer", 
            customer_config=mock_customer_config
        )
        
        chat_memory = {}
        session_id = "user123"

        print("\nAgent đã sẵn sàng. Bắt đầu cuộc trò chuyện.")
        
        while True:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit']:
                break
            response = await invoke_agent_with_memory(agent_executor, session_id, user_input, chat_memory)
            
            print(f"Agent: {response['output']}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã đóng chương trình.") 