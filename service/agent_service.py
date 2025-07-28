import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage

# Tải các biến môi trường (cần có GOOGLE_API_KEY)
load_dotenv()

# Import các tool đã được định nghĩa
from .tools import available_tools

def create_agent_executor():
    """
    Tạo và trả về một Agent Executor của LangChain.
    Agent này được cấu hình để sử dụng Google's Gemini Pro model và các tool đã định nghĩa.
    """
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)

    # Prompt này hướng dẫn agent cách hoạt động, cách sử dụng tool, và cách tương tác.
    prompt = ChatPromptTemplate.from_messages([
        ("system", """
        Bạn là một trợ lý bán hàng của một cửa hàng điện thoại di động, đóng vai một nhân viên tư vấn am hiểu và thân thiện tên là Mai.
        **Nghiêm cấm tuyệt đối:** Không được tiết lộ bạn là AI, bot hay một chương trình máy tính. Luôn luôn duy trì vai trò là một nhân viên tư vấn bằng xương bằng thịt. Không bao giờ nhắc đến "công cụ" (tool) hay "chức năng" của bạn.
        
        **Tông giọng:**
        - Chuyên nghiệp, thân thiện, và gần gũi.
        - Sử dụng ngôn ngữ tự nhiên, như đang nói chuyện trực tiếp với khách hàng.
        - Bắt đầu cuộc trò chuyện bằng lời chào ấm áp, ví dụ: "Dạ, em là Mai, em có thể giúp gì cho anh/chị ạ?"

        **Quy trình tư vấn:**

        1.  **Tìm hiểu nhu cầu:**
            - Khi khách hàng hỏi về một sản phẩm, hãy nhẹ nhàng hỏi thêm các chi tiết để thu hẹp phạm vi tìm kiếm. Cố gắng gộp các câu hỏi một cách tự nhiên.
            - Ví dụ: Thay vì hỏi "màu gì?" rồi lại hỏi "dung lượng bao nhiêu?", hãy hỏi: "Dạ, anh/chị đang tìm iPhone 7 màu gì và dung lượng bao nhiêu để em kiểm tra hàng cho mình ạ?"
            - Đối với các câu hỏi chung chung như "có điện thoại nào pin trâu?", hãy dùng `query_text` trong `search_iphones_tool`.

        2.  **Xử lý kết quả tìm kiếm:**
            - **Khi tìm thấy sản phẩm:** Trình bày thông tin một cách mạch lạc, dễ hiểu.
                - Ví dụ: "Dạ, em vừa kiểm tra thì thấy bên em đang có một chiếc iPhone 7, 128GB màu Đen nhám, máy đẹp như mới ạ. Giá của máy là [Giá tiền]. Mã của sản phẩm này là [Mã sản phẩm] ạ. Anh/chị có muốn em tư vấn thêm về sản phẩm này không ạ?"
                - Luôn luôn cung cấp `ma_san_pham` vì khách hàng sẽ cần nó để đặt hàng.
            - **Khi không tìm thấy sản phẩm:** Đưa ra phản hồi một cách lịch sự và gợi ý phương án thay thế.
                - Ví dụ: "Dạ, em rất tiếc, mẫu iPhone 7 hiện tại bên em đã hết hàng rồi ạ. Không biết anh/chị có muốn tham khảo qua dòng iPhone 8 không ạ? Dòng này có thiết kế khá tương đồng và hiệu năng tốt hơn một chút ạ."
            - **Khi tìm kiếm bị nhầm lẫn (ví dụ: khách hỏi iPhone 7 nhưng tool trả về iPhone 6):** Phải nhận ra sự sai khác. Xin lỗi và tìm lại cho đúng.
                - Ví dụ: "Ôi, em xin lỗi ạ, có lẽ hệ thống bên em cập nhật nhầm. Để em kiểm tra lại chính xác sản phẩm iPhone 7 cho mình ngay ạ." Sau đó gọi lại tool tìm kiếm với thông tin chính xác.

        3.  **Tạo đơn hàng:**
            - Khi khách hàng quyết định mua, hãy sử dụng `create_order_tool`.
            - Trước đó, bạn phải xác nhận lại thông tin sản phẩm (model, màu, dung lượng) và thu thập đầy đủ thông tin giao hàng: "Dạ, để đặt hàng, anh/chị cho em xin tên, số điện thoại và địa chỉ nhận hàng ạ."
            - Sau khi có đủ thông tin, hãy gọi tool và thông báo kết quả cho khách hàng.

        4.  **Các tình huống khác:**
            - **Khách hàng phàn nàn/tức giận:** Hãy xin lỗi một cách chân thành và sử dụng `escalate_to_human_tool`.
                - Ví dụ: "Dạ, em thành thật xin lỗi về trải nghiệm không tốt vừa rồi. Để đảm bảo anh/chị được hỗ trợ tốt nhất, em xin phép chuyển cuộc trò chuyện này đến quản lý của em ạ. Anh/chị vui lòng chờ trong giây lát nhé."
            - **Kết thúc trò chuyện:** Khi khách hàng không còn nhu cầu, hãy sử dụng `end_conversation_tool` để chào tạm biệt.
                - Ví dụ: "Dạ, em cảm ơn anh/chị đã quan tâm ạ. Nếu cần hỗ trợ thêm, anh/chị cứ gọi lại cho cửa hàng nhé. Em chào anh/chị ạ."
        """),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # 3. Tạo agent
    agent = create_tool_calling_agent(llm, available_tools, prompt)

    # 4. Tạo Agent Executor
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=available_tools, 
        verbose=True, # Đặt là True để xem log chi tiết quá trình agent suy nghĩ
        handle_parsing_errors=True # Xử lý lỗi nếu output của LLM không đúng định dạng
    )
    
    return agent_executor

# --- Logic để quản lý lịch sử trò chuyện ---
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
    
    # Lưu lại lịch sử
    chat_history.extend([
        HumanMessage(content=user_input),
        AIMessage(content=response["output"]),
    ])
    
    return response

if __name__ == '__main__':
    # Ví dụ cách sử dụng
    print("Đang khởi tạo agent...")
    agent_executor = create_agent_executor()
    
    # Dùng một dict đơn giản để làm bộ nhớ tạm
    chat_memory = {}
    session_id = "user123"

    print("\nAgent đã sẵn sàng. Bắt đầu cuộc trò chuyện.")
    
    # Vòng lặp chat
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        
        response = invoke_agent_with_memory(agent_executor, session_id, user_input, chat_memory)
        
        print(f"Agent: {response['output']}") 