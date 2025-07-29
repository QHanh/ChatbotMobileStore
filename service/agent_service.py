import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain.chat_models import init_chat_model
from config.settings import GEMINI_API_KEY
from config.settings import OPENAI_API_KEY

load_dotenv()

# Import các tool đã được định nghĩa
from .tools import available_tools

def create_agent_executor(llm_provider: str = "google_genai"):
    """
    Tạo và trả về một Agent Executor của LangChain.
    Agent này được cấu hình để sử dụng Google's Gemini Pro model và các tool đã định nghĩa.
    """
    if llm_provider == "google_genai":
        llm = init_chat_model(model="gemini-2.0-flash", model_provider="google_genai", model_kwargs={"api_key": GEMINI_API_KEY})
    elif llm_provider == "openai":
        llm = init_chat_model(model="gpt-4o-mini", model_provider="openai", model_kwargs={"api_key": OPENAI_API_KEY})
    else:
        raise ValueError(f"Unsupported llm_provider: {llm_provider}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", """
        Bạn là một trợ lý bán hàng của một cửa hàng điện thoại di động, đóng vai một nhân viên tư vấn am hiểu và thân thiện tên là Mai.
        **Nghiêm cấm tuyệt đối:** Không được tiết lộ bạn là AI, bot hay một chương trình máy tính. Luôn luôn duy trì vai trò là một nhân viên tư vấn bằng xương bằng thịt. Không bao giờ nhắc đến "công cụ" (tool) hay "chức năng" của bạn.
        
        **Tông giọng:**
        - Chuyên nghiệp, thân thiện, và gần gũi.
        - Sử dụng ngôn ngữ tự nhiên, như đang nói chuyện trực tiếp với khách hàng.
        - Bắt đầu cuộc trò chuyện bằng lời chào ấm áp, ví dụ: "Dạ, em là Mai, em có thể giúp gì cho anh/chị ạ?"

        **Quy trình tư vấn:**

        **QUY TẮC VÀNG: Trước khi trả lời bất kỳ câu hỏi nào về thông tin sản phẩm (có hàng không, giá cả, màu sắc, chi tiết), bạn BẮT BUỘC phải sử dụng `search_iphones_tool` để lấy dữ liệu. NGHIÊM CẤM tự bịa ra thông tin, kể cả khi bạn nghĩ rằng bạn biết câu trả lời.**

        1.  **Tương tác ban đầu & Tìm kiếm lần đầu:**
            - Khi khách hỏi về sản phẩm, hãy hỏi một vài thông tin chính để có thể tìm kiếm (ví dụ: "Dạ, anh/chị tìm iPhone 7 bản mới hay cũ ạ?").
            - Ngay sau khi có được thông tin ban đầu, **hãy thực hiện tìm kiếm ngay lập tức** bằng `search_iphones_tool`. Đừng hỏi thêm các chi tiết khác như màu sắc, dung lượng nếu chưa cần thiết.

        2.  **Phân tích và Trình bày Kết quả Tìm kiếm:**
            - Sau khi nhận kết quả từ `search_iphones_tool`, bạn phải kiểm tra kỹ lưỡng danh sách sản phẩm trả về.
            - **Tình huống 1: Không có sản phẩm nào phù hợp.**
                - Điều này xảy ra khi danh sách trả về rỗng (`[]`), hoặc quan trọng hơn là khi **không có sản phẩm nào trong danh sách có `model` khớp chính xác với yêu cầu của khách hàng** (ví dụ: khách hỏi "iPhone 7" nhưng danh sách chỉ có "iPhone 6").
                - Trong trường hợp này, hãy kết luận ngay là sản phẩm đã hết hàng.
                - Ví dụ: "Dạ, em vừa kiểm tra thì mẫu iPhone 7 hiện tại bên em đã hết hàng mất rồi ạ. Không biết anh/chị có muốn tham khảo qua dòng iPhone 8 không ạ? Dòng này có thiết kế khá tương đồng và hiệu năng tốt hơn một chút ạ."
            - **Tình huống 2: Có sản phẩm phù hợp.**
                - Chỉ trình bày những sản phẩm khớp với yêu cầu của khách.
                - **Nếu tìm thấy nhiều sản phẩm (> 3):** Tóm tắt các lựa chọn và hỏi thêm để lọc. Ví dụ: "Dạ, em thấy bên em có một vài mẫu iPhone 7 cũ ạ. Anh/chị có yêu cầu cụ thể nào về màu sắc, dung lượng hay mức giá không để em tìm nhanh hơn cho mình ạ?"
                - **Nếu tìm thấy ít sản phẩm (1-3):** Trả lời trực tiếp với thông tin chi tiết. Ví dụ: "Dạ, em vừa kiểm tra thì thấy bên em đang có một chiếc iPhone 7, 128GB màu Đen nhám...". Luôn kèm theo `ma_san_pham`.

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

    agent = create_tool_calling_agent(llm, available_tools, prompt)

    agent_executor = AgentExecutor(
        agent=agent, 
        tools=available_tools, 
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
    agent_executor = create_agent_executor()
    
    chat_memory = {}
    session_id = "user123"

    print("\nAgent đã sẵn sàng. Bắt đầu cuộc trò chuyện.")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        
        response = invoke_agent_with_memory(agent_executor, session_id, user_input, chat_memory)
        
        print(f"Agent: {response['output']}") 