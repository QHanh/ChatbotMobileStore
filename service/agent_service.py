import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain.chat_models import init_chat_model
import getpass
from functools import partial

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
  os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter API key for Google Gemini: ")

from .tools import create_customer_tools

def create_agent_executor(
    customer_id: str,
    customer_configs: dict,
    llm_provider: str = "google_genai"
):
    """
    Tạo và trả về một Agent Executor của LangChain, được cấu hình cho một khách hàng cụ thể.
    """
    if llm_provider == "google_genai":
        llm = init_chat_model(model="gemini-2.0-flash", model_provider="google_genai")
    elif llm_provider == "openai":
        llm = init_chat_model(model="gpt-4o-mini", model_provider="openai")
    else:
        raise ValueError(f"Unsupported llm_provider: {llm_provider}")

    config = customer_configs.get(customer_id, {})
    persona = config.get("persona", {"ai_name": "Mai", "ai_role": "trợ lý ảo"})
    custom_prompt_text = config.get("custom_prompt", "")
    service_feature_enabled = config.get("service_feature_enabled", True) # Mặc định bật

    customer_tools = create_customer_tools(customer_id, service_feature_enabled)

    # 1. Hướng dẫn cơ bản với Quy tắc Tối thượng
    base_instructions = f"""
    Bạn là một chuyên gia tư vấn của một cửa hàng điện thoại, đóng vai một {persona['ai_role']} am hiểu và thân thiện tên là {persona['ai_name']}.
    Nhiệm vụ của bạn là tra cứu thông tin sản phẩm và dịch vụ **CHỈ** từ kho dữ liệu của cửa hàng bằng các công cụ được cung cấp.

    **QUY TẮC TỐI THƯỢNG (TUYỆT ĐỐI TUÂN THỦ):**
    1.  **BẠN KHÔNG CÓ KIẾN THỨC RIÊNG.** Toàn bộ kiến thức của bạn về sản phẩm, dịch vụ, và tồn kho đều đến từ công cụ.
    2.  **LUÔN DÙNG CÔNG CỤ.** Với **MỌI** câu hỏi của khách hàng liên quan đến một sản phẩm hoặc dịch vụ (ví dụ: "iPhone 16", "thay pin"), bạn phải **NGAY LẬP TỨC** sử dụng công cụ tìm kiếm.
    3.  **KHÔNG GIẢ ĐỊNH.** Kể cả khi một sản phẩm nghe có vẻ không có thật (như trong hình ảnh "iPhone 16" vào tháng 7/2025), bạn vẫn phải dùng công cụ để kiểm tra. Nếu công cụ không tìm thấy gì, nghĩa là cửa hàng không có sản phẩm đó.
    4.  **KHÔNG TIẾT LỘ VAI TRÒ.** Nghiêm cấm tuyệt đối tiết lộ bạn là AI hay bot.
    """

    # 2. Hướng dẫn quy trình làm việc dựa trên tính năng
    if service_feature_enabled:
        workflow_instructions = """
    **Quy trình làm việc:**
    1.  Xác định khách muốn tìm **sản phẩm** hay **dịch vụ**.
    2.  Sử dụng công cụ tìm kiếm tương ứng (`search_products_tool` hoặc `search_services_tool`).
    3.  **Xử lý kết quả:**
        - Nếu công cụ trả về danh sách rỗng (`[]`), thông báo cho khách là sản phẩm/dịch vụ đó hiện **không có tại cửa hàng** và gợi ý lựa chọn khác. Ví dụ: "Dạ em rất tiếc, bên em hiện không có iPhone 16 ạ. Anh/chị có muốn tham khảo các dòng iPhone 15 không ạ?"
        - Nếu có kết quả, trình bày thông tin cho khách.
    4.  Khi khách chốt đơn, sử dụng công cụ tạo đơn hàng tương ứng.
        """
    else:
        workflow_instructions = """
    **Quy trình làm việc:**
    1.  Với mọi câu hỏi về sản phẩm, dùng `search_products_tool`.
    2.  **Xử lý kết quả:**
        - Nếu công cụ trả về danh sách rỗng (`[]`) hoặc không có kết quả nào giống với yêu cầu của khách hàng, thông báo cho khách là mẫu sản phẩm đó hiện **không có tại cửa hàng** và có thể gợi ý lựa chọn khác trong trường hợp nếu có dữ liệu về mẫu sản phẩm khác có cùng model được tìm thấy bằng công cụ. Ví dụ: "Dạ em rất tiếc, bên em hiện không còn chiếc iPhone 16 Pro Max màu đỏ nào ạ. Anh/chị có muốn tham khảo các dòng iPhone 16 khác không ạ?"
        - Nếu có kết quả, trình bày thông tin cho khách.
    3.  Khi khách chốt mua sản phẩm, dùng `create_order_product_tool`.
        """

    other_instructions = """
    **Các tình huống khác:**
        - **Khách hàng phàn nàn/tức giận:** Hãy xin lỗi và sử dụng `escalate_to_human_tool`.
        - **Kết thúc trò chuyện:** Khi khách hàng không còn nhu cầu, hãy sử dụng `end_conversation_tool`.
    """

    # Nối các phần lại với nhau
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

def invoke_agent_with_memory(agent_executor, session_id: str, user_input: str, memory: dict):
    """
    Gọi agent bất đồng bộ với input của người dùng và quản lý lịch sử trò chuyện.
    """
    chat_history = get_session_history(session_id, memory)
    
    response = agent_executor.invoke({
        "input": user_input,
        "chat_history": chat_history
    })
    
    chat_history.extend([
        HumanMessage(content=user_input),
        AIMessage(content=response["output"]),
    ])
    
    return response

if __name__ == '__main__':
    print("Đang khởi tạo agent...")
    agent_executor = create_agent_executor(customer_id="test_customer", customer_configs={})
    
    chat_memory = {}
    session_id = "user123"

    print("\nAgent đã sẵn sàng. Bắt đầu cuộc trò chuyện.")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        response = invoke_agent_with_memory(agent_executor, session_id, user_input, chat_memory)
        
        print(f"Agent: {response['output']}") 