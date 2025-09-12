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
from database.database import Customer, SystemInstruction, ChatHistory, ChatThread
from service.retrieve.search_service import search_faqs

def create_agent_executor(
    es_client: AsyncElasticsearch,
    db: Session,
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
        product_feature_enabled,
        service_feature_enabled, 
        accessory_feature_enabled,
        llm=llm
    )

    identity = ""
    if persona['ai_role']:
        identity = f"đóng vai là một {persona['ai_role']} am hiểu và thân thiện"
    if persona['ai_name']:
        identity += f" tên là {persona['ai_name']}"
        
    db_instructions = db.query(SystemInstruction).all()
    instructions_dict = {instr.key: instr.value for instr in db_instructions}

    indentity_instructions = f"""
        Bạn là một chuyên gia tư vấn của một cửa hàng điện thoại, {identity}.
        Luôn xưng hô là "em" và gọi khách hàng là "anh/chị". Khi nói về cửa hàng, hãy dùng "bên em".
        Khi mô tả sản phẩm, hãy tránh dùng các đại từ nhân xưng như "tôi" hay "mình". Thay vào đó, hãy mô tả một cách khách quan, ví dụ: "sản phẩm có...", "máy được trang bị...".
    """
    base_instructions = instructions_dict.get("base_instructions", "")

    product_workflow = instructions_dict.get("product_workflow", "")
    service_workflow = instructions_dict.get("service_workflow", "")
    accessory_workflow = instructions_dict.get("accessory_workflow", "")

    workflow_steps = []
    if product_feature_enabled:
        workflow_steps.append(product_workflow)
    if service_feature_enabled:
        workflow_steps.append(service_workflow)
    if accessory_feature_enabled:
        workflow_steps.append(accessory_workflow)
    
    workflow_instructions = f"""
    **Quy trình làm việc:**
    1. Xác định nhu cầu của khách: **sản phẩm**, **dịch vụ**, hay **linh kiện/phụ kiện**.
    2. Sử dụng công cụ tìm kiếm tương ứng:
       {'\n   '.join(workflow_steps)}
    """

    offerings = []
    if product_feature_enabled:
        offerings.append("bán điện thoại")
    if service_feature_enabled:
        offerings.append("sửa chữa điện thoại")
    if accessory_feature_enabled:
        offerings.append("bán phụ kiện")

    if len(offerings) > 2:
        offerings_str = ", ".join(offerings[:-1]) + f" và {offerings[-1]}"
    elif len(offerings) == 2:
        offerings_str = " và ".join(offerings)
    else:
        offerings_str = offerings[0] if offerings else ""

    general_query_instruction = f"""
    **Xử lý câu hỏi chung:**
    - Khi người dùng hỏi những câu chung chung như "shop có gì?", "bên bạn có dịch vụ gì?", "bạn bán gì vậy?" mà không cung cấp chi tiết cụ thể, **KHÔNG SỬ DỤNG CÔNG CỤ TÌM KIẾM**.
    - Thay vào đó, hãy trả lời trực tiếp bằng cách tóm tắt các dịch vụ của cửa hàng. Dựa trên các chức năng đang được bật, câu trả lời của bạn nên là: "Dạ bên em chuyên {offerings_str} ạ. Anh/chị đang quan tâm đến mảng nào ạ?"
    """

    faq_instruction = """
    **Quy trình ưu tiên FAQ:**
    - Hệ thống đã tìm kiếm trước trong kho Câu hỏi thường gặp (FAQ) và có thể đã cung cấp một cặp câu hỏi-trả lời có sẵn trong context.
    - **Ưu tiên tuyệt đối:** Hãy xem xét kỹ thông tin này trước tiên.
    - Nếu câu trả lời được gợi ý thực sự phù hợp với câu hỏi của người dùng và ngữ cảnh cuộc trò chuyện, hãy sử dụng nó làm cơ sở để trả lời. Bạn có thể diễn đạt lại cho tự nhiên hơn.
    - Nếu câu trả lời không phù hợp, hãy bỏ qua nó và sử dụng các công cụ khác để tìm thông tin.
    """
    
    workflow_instructions_add = instructions_dict.get("workflow_instructions", "")
    
    other_instructions = instructions_dict.get("other_instructions", "")

    custom_prompt_section = ""
    if custom_prompt_text:
        custom_prompt_section = f'''
**Lưu ý đặc biệt từ chủ cửa hàng (Strictly follow this):**
{custom_prompt_text}
'''

    final_system_prompt = "\n".join(filter(None, [
        indentity_instructions,
        base_instructions,
        workflow_instructions,
        general_query_instruction,
        workflow_instructions_add,
        faq_instruction,
        other_instructions,
        custom_prompt_section
    ]))

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
        handle_parsing_errors=True
    )
    
    return agent_executor

def get_session_history(customer_id: str, session_id: str, db: Session) -> List[BaseMessage]:
    """Lấy lịch sử chat từ database."""
    history_records = db.query(ChatHistory).filter(
        ChatHistory.customer_id == customer_id,
        ChatHistory.thread_id == session_id
    ).order_by(ChatHistory.id).all()

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
    
    if faq_results:
        found_faq = faq_results[0]
        faq_prompt = f"""--- GỢI Ý TỪ FAQ ---
Câu hỏi tương tự đã tìm thấy: "{found_faq['question']}"
Câu trả lời có sẵn (chỉ trả lời theo câu này nếu bạn thấy phù hợp): "{found_faq['answer']}"
--- HẾT GỢI Ý ---"""
        faq_context.append(HumanMessage(content=faq_prompt))

    chat_history = get_session_history(customer_id, session_id, db)
    
    def format_history_for_llm(history: List[BaseMessage]) -> List[str]:
        formatted = []
        for msg in history:
            role = "Người dùng" if isinstance(msg, HumanMessage) else "Trợ lý"
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
        message=response["output"]
    )
    db.add(ai_message)
    
    db.commit()
    
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
            SystemInstruction(key='accessory_workflow', value="-   Khi khách hỏi về **linh kiện / phụ kiện** (ốp lưng, sạc, tai nghe, ...), dùng `search_accessories_tool`."),
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