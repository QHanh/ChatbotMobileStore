import uuid
from service.agent_service import create_agent_executor, invoke_agent_with_memory

def main():
    """
    Hàm chính để chạy ứng dụng chatbot trên giao diện dòng lệnh (CLI).
    """
    print("--- Chào mừng đến với Chatbot Bán hàng iPhone ---")
    print("Đang khởi tạo Agent, vui lòng chờ...")

    try:
        agent_executor = create_agent_executor()
        print("✅ Agent đã sẵn sàng! Bắt đầu cuộc trò chuyện.")
        print("Gõ 'quit' hoặc 'exit' để thoát.")
        print("-" * 50)
    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng khi khởi tạo agent: {e}")
        print("Vui lòng kiểm tra lại GOOGLE_API_KEY và các cấu hình khác.")
        return

    # Sử dụng một dict đơn giản để làm bộ nhớ tạm, lưu trữ lịch sử chat
    # Key là session_id, value là list các message
    chat_memory = {}
    
    # Tạo một session ID ngẫu nhiên cho mỗi lần chạy
    session_id = str(uuid.uuid4())

    # Vòng lặp chat
    while True:
        try:
            user_input = input("🙂 Bạn: ")
            if user_input.lower().strip() in ['exit', 'quit', 'bye']:
                print("🤖 Agent: Cảm ơn bạn đã sử dụng dịch vụ. Hẹn gặp lại!")
                break
            
            response = invoke_agent_with_memory(
                agent_executor, 
                session_id, 
                user_input, 
                chat_memory
            )
            
            print(f"🤖 Agent: {response['output']}")

        except KeyboardInterrupt:
            print("\n🤖 Agent: Tạm biệt! Hẹn gặp lại.")
            break
        except Exception as e:
            print(f" Rất tiếc, đã có lỗi xảy ra: {e}")
            print(" Vui lòng thử lại.")

if __name__ == "__main__":
    main() 