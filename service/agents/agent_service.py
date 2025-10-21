from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain.chat_models import init_chat_model
from sqlalchemy.orm import Session
from elasticsearch import AsyncElasticsearch
from typing import List

load_dotenv()

from service.utils.tools import create_customer_tools
from database.database import Customer, ChatHistory, ChatThread
from service.retrieve.search_service import search_faqs
from service.prompts.prompt_service import compose_system_prompt, load_instructions

def create_agent_executor(
    es_client: AsyncElasticsearch,
    db: Session,
    customer_id: str,
    customer_config: Customer,
    thread_id: str = None,
    llm_provider: str = "google_genai",
    api_key: str = None
):
    """
    Tạo và trả về một Agent Executor, được cấu hình cho một khách hàng cụ thể.
    """
    if not api_key:
        raise ValueError("Bạn chưa thêm API key bên trang cấu hình.")

    if llm_provider == "google_genai":
        llm = init_chat_model(model="gemini-2.5-flash", model_provider="google_genai", api_key=api_key)
    elif llm_provider == "openai":
        llm = init_chat_model(model="gpt-4o-mini", model_provider="openai", api_key=api_key)
    else:
        raise ValueError(f"Không tìm thấy LLM provider: {llm_provider}")

    persona = {"ai_name": customer_config.ai_name, "ai_role": customer_config.ai_role}
    custom_prompt_text = customer_config.custom_prompt or ""
    product_feature_enabled = customer_config.product_feature_enabled
    service_feature_enabled = customer_config.service_feature_enabled
    accessory_feature_enabled = customer_config.accessory_feature_enabled

    customer_tools = create_customer_tools(
        es_client, 
        customer_id, 
        thread_id,
        product_feature_enabled,
        service_feature_enabled, 
        accessory_feature_enabled,
        llm=llm
    )

    final_system_prompt = compose_system_prompt(
        db=db,
        customer_config=customer_config,
        product_feature_enabled=product_feature_enabled,
        service_feature_enabled=service_feature_enabled,
        accessory_feature_enabled=accessory_feature_enabled,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", final_system_prompt),
        MessagesPlaceholder(variable_name="faq_context", optional=True),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad", optional=True),
    ])

    agent = create_tool_calling_agent(llm, customer_tools, prompt)

    agent_executor = AgentExecutor(
        agent=agent, 
        tools=customer_tools, 
        verbose=True,
        handle_parsing_errors=True,
        return_intermediate_steps=True
    )
    
    return agent_executor

def get_session_history(customer_id: str, session_id: str, db: Session, limit: int = 8) -> List[BaseMessage]:
    """Lấy các tin nhắn gần nhất trong lịch sử chat từ database."""
    history_records = db.query(ChatHistory).filter(
        ChatHistory.customer_id == customer_id,
        ChatHistory.thread_id == session_id
    ).order_by(ChatHistory.id.desc()).limit(limit).all()

    # Đảo ngược lại để có thứ tự từ cũ đến mới
    history_records.reverse()

    messages: List[BaseMessage] = []
    for record in history_records:
        if record.role == 'human':
            messages.append(HumanMessage(content=record.message))
        elif record.role == 'bot':
            messages.append(AIMessage(content=record.message))
    return messages

async def invoke_agent_with_memory(agent_executor, customer_id: str, session_id: str, user_input: str, db: Session, es_client: AsyncElasticsearch):
    """
    Gọi agent với input của người dùng và quản lý lịch sử trò chuyện trong database.
    Luôn kiểm tra FAQ trước tiên.
    """
    faq_context = []
    faq_results = await search_faqs(es_client=es_client, customer_id=customer_id, query=user_input)
    instr = load_instructions(db)
    
    if faq_results:
        found_faq = faq_results[0]
        template = instr.get(
            "faq_context_template",
            """--- GỢI Ý TỪ FAQ ---
Câu hỏi tương tự đã tìm thấy: "{question}"
Câu trả lời có sẵn (chỉ trả lời theo câu này nếu bạn thấy phù hợp): "{answer}{image_text}"
--- HẾT GỢI Ý ---"""
        )
        image_text = ""
        if 'image' in found_faq and found_faq['image']:
            image_text = f". Hình ảnh kèm theo: {found_faq['image']}. Khi đưa ra link ảnh bạn cần để mỗi link ảnh trên một dòng."
        faq_prompt = (
            template
            .replace("{question}", str(found_faq.get('question', "")))
            .replace("{answer}", str(found_faq.get('answer', "")))
            .replace("{image_text}", image_text)
        )
        faq_context.append(HumanMessage(content=faq_prompt))

    chat_history = get_session_history(customer_id, session_id, db)
    
    user_label = instr.get("chat_history_role_user", "Người dùng")
    ai_label = instr.get("chat_history_role_ai", "Trợ lý")

    def format_history_for_llm(history: List[BaseMessage]) -> List[str]:
        formatted = []
        for msg in history:
            role = user_label if isinstance(msg, HumanMessage) else ai_label
            formatted.append(f"{role}: {msg.content}")
        return formatted

    formatted_history = format_history_for_llm(chat_history)

    search_tool_names = ["search_products_tool", "search_services_tool", "search_accessories_tool"]
    for tool in agent_executor.tools:
        if tool.name in search_tool_names:
            tool.coroutine.keywords['original_query'] = user_input
            tool.coroutine.keywords['chat_history'] = formatted_history

    response = await agent_executor.ainvoke({
        "input": user_input,
        "chat_history": chat_history,
        "faq_context": faq_context,
        "thread_id": session_id,
    })

    print("--- AGENT RESPONSDED ---")
    # print(response)
    # print("----------------------")

    # Lấy output một cách an toàn
    if 'output' not in response or not response['output']:
        print(f"[ERROR] Agent response is empty or does not contain 'output' key: {response}")
        output_message = 'Em chưa hiểu rõ yêu cầu của anh/chị. Anh/chị có thể nói lại được không ạ?'
    else:
        output_message = response['output']
    
    chat_thread = db.query(ChatThread).filter(
        ChatThread.customer_id == customer_id,
        ChatThread.thread_id == session_id
    ).first()
    thread_name = chat_thread.thread_name if chat_thread else None

    human_message = ChatHistory(
        customer_id=customer_id,
        thread_id=session_id,
        thread_name=thread_name,
        role="human",
        message=user_input
    )
    db.add(human_message)

    ai_message = ChatHistory(
        customer_id=customer_id,
        thread_id=session_id,
        thread_name=thread_name,
        role="bot",
        message=output_message
    )
    db.add(ai_message)
    
    db.commit()
    
    # Đảm bảo response trả về luôn có 'output'
    response['output'] = output_message
    return response

def clear_chat_history_for_customer(customer_id: str, db: Session):
    """Xóa toàn bộ lịch sử chat cho một customer_id cụ thể từ DB."""
    try:
        num_deleted = db.query(ChatHistory).filter(ChatHistory.customer_id == customer_id).delete(synchronize_session=False)
        db.commit()
        print(f"Cleared {num_deleted} chat message(s) for customer {customer_id}")
        return {"status": "success", "message": f"Cleared {num_deleted} chat message(s) for customer {customer_id}"}
    except Exception as e:
        db.rollback()
        print(f"Error clearing chat history for {customer_id}: {e}")
        raise

if __name__ == '__main__':
    import asyncio

    async def main():
        print("Đang khởi tạo agent...")
        mock_customer_config = Customer(
            customer_id="test_customer",
            ai_name="TestBot",
            ai_role="trợ lý ảo test",
            custom_prompt="Luôn trả lời bằng tiếng Việt.",
            product_feature_enabled=True,
            service_feature_enabled=True,
            accessory_feature_enabled=False
        )
        from database.database import SessionLocal
        db_session = SessionLocal()
        
        from database.database import SystemInstruction
        mock_instructions = [
            SystemInstruction(key='base_instructions', value="Bạn là một chuyên gia tư vấn của một cửa hàng điện thoại, {identity}."),
            SystemInstruction(key='product_workflow', value="-   Khi khách hỏi về **sản phẩm** (điện thoại, máy tính bảng, ...), dùng `search_products_tool`."),
            SystemInstruction(key='service_workflow', value="-   Khi khách hỏi về **dịch vụ** (sửa chữa, thay pin, ...), dùng `search_services_tool`."),
            SystemInstruction(key='accessory_workflow', value="-   Khi khách hỏi về **linh kiện / phụ kiện** (ốp lưng, sạc, tai nghe, ...), dùng `search_accessories_tool`. Nếu khách chốt mua, dùng `create_order_accessory_tool`."),
            SystemInstruction(key='workflow_instructions', value="**Quy trình làm việc:**\n{workflow_steps}"),
            SystemInstruction(key='other_instructions', value="**Các tình huống khác:**")
        ]
        for instr in mock_instructions:
            existing = db_session.query(SystemInstruction).filter_by(key=instr.key).first()
            if existing:
                existing.value = instr.value
            else:
                db_session.add(instr)
        db_session.commit()

        es_client = AsyncElasticsearch()

        agent_executor = create_agent_executor(
            es_client=es_client,
            db=db_session,
            customer_id="test_customer", 
            customer_config=mock_customer_config
        )
        
        session_id = "user123"

        print("\nAgent đã sẵn sàng. Bắt đầu cuộc trò chuyện.")
        
        while True:
            user_input = input("You: ")
            if user_input.lower() in ['exit', 'quit']:
                break
            response = await invoke_agent_with_memory(
                agent_executor, 
                mock_customer_config.customer_id,
                session_id, 
                user_input, 
                db_session,
                es_client
            )
            
            print(f"Agent: {response['output']}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã đóng chương trình.") 