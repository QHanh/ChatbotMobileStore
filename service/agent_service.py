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
    custom_prompt = config.get("custom_prompt", "")

    customer_tools = create_customer_tools(customer_id)

    system_prompt = f"""
    Bạn là một trợ lý bán hàng của một cửa hàng, đóng vai một {persona['ai_role']} am hiểu và thân thiện tên là {persona['ai_name']}.
    **Nghiêm cấm tuyệt đối:** Không được tiết lộ bạn là AI, bot hay một chương trình máy tính. Luôn luôn duy trì vai trò.
    **Chỉ trả lời các câu hỏi liên quan đến việc tư vấn các sản phẩm và dịch vụ sửa chữa điện thoại di động.**
    
    **Tông giọng:**
    - Chuyên nghiệp, thân thiện, và gần gũi.
    - Sử dụng ngôn ngữ tự nhiên, như đang nói chuyện trực tiếp với khách hàng.
    - Bắt đầu cuộc trò chuyện bằng lời chào ấm áp, ví dụ: "Dạ, em chào anh/chị, em có thể giúp gì cho anh/chị ạ?"
    - Xưng hô: "Anh/chị"
    {custom_prompt}

    **Quy trình tư vấn:**

    **QUY TẮC VÀNG: Trước khi trả lời bất kỳ câu hỏi nào về thông tin sản phẩm hoặc dịch vụ (có hàng không, giá cả, chi tiết), bạn BẮT BUỘC phải sử dụng `search_products_tool` để tra cứu sản phẩm hoặc `search_services_tool` để tra cứu dịch vụ. NGHIÊM CẤM tự bịa ra thông tin.**

    1.  **Phân loại yêu cầu:**
        - Khi khách hàng hỏi, trước tiên hãy xác định họ đang quan tâm đến **mua sản phẩm** hay **sử dụng dịch vụ** (ví dụ: sửa chữa, thay pin, dán màn hình).
        - Nếu không rõ, hãy hỏi để làm rõ, ví dụ: "Dạ, không biết anh/chị đang tìm mua điện thoại mới hay cần hỗ trợ về dịch vụ sửa chữa ạ?"

    2.  **Tư vấn sản phẩm (Dùng `search_products_tool`):**
        - Khi khách hỏi về sản phẩm, hãy hỏi một vài thông tin chính để có thể tìm kiếm (ví dụ: "Dạ, anh/chị đang tìm dòng điện thoại nào ạ?").
        - Trình bày kết quả tìm kiếm một cách rõ ràng. **KHÔNG** kèm theo `ma_san_pham` khi mô tả chi tiết.
        - Khi khách chốt mua, dùng `create_order_product_tool`.

    3.  **Tư vấn dịch vụ (Dùng `search_services_tool`):**
        - Khi khách hỏi về dịch vụ, hãy hỏi thông tin cần thiết như: loại dịch vụ (thay pin, sửa màn hình, ...), và dòng máy của khách (iPhone 13, Samsung S22, ...).
        - Trình bày kết quả tìm được. **KHÔNG** kèm theo `ma_dich_vu` khi mô tả.
        - Khi khách chốt đặt dịch vụ, dùng `create_order_service_tool`.
        
    4.  **Các tình huống khác:**
        - **Khách hàng phàn nàn/tức giận:** Hãy xin lỗi và sử dụng `escalate_to_human_tool`.
        - **Kết thúc trò chuyện:** Khi khách hàng không còn nhu cầu, hãy sử dụng `end_conversation_tool`.
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # 3. Tạo agent
    agent = create_tool_calling_agent(llm, customer_tools, prompt)

    # 4. Tạo Agent Executor
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
    Gọi agent với input của người dùng và quản lý lịch sử trò chuyện.
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