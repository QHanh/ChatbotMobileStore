import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain.chat_models import init_chat_model
import getpass
from functools import partial
from sqlalchemy.orm import Session
from elasticsearch import AsyncElasticsearch

load_dotenv()

from service.utils.tools import create_customer_tools
from database.database import Customer, SystemInstruction

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
        llm = init_chat_model(model="gemini-2.0-flash", model_provider="google_genai", api_key=api_key)
    elif llm_provider == "openai":
        llm = init_chat_model(model="gpt-4o-mini", model_provider="openai", api_key=api_key)
    else:
        raise ValueError(f"Không tìm thấy LLM provider: {llm_provider}")

    persona = {"ai_name": customer_config.ai_name, "ai_role": customer_config.ai_role}
    custom_prompt_text = customer_config.custom_prompt or ""
    service_feature_enabled = customer_config.service_feature_enabled
    accessory_feature_enabled = customer_config.accessory_feature_enabled

    customer_tools = create_customer_tools(es_client, customer_id, service_feature_enabled, accessory_feature_enabled)

    identity = ""
    if persona['ai_role']:
        identity = f"đóng vai là một {persona['ai_role']} am hiểu và thân thiện"
    if persona['ai_name']:
        identity += f" tên là {persona['ai_name']}"
        
    db_instructions = db.query(SystemInstruction).all()
    instructions_dict = {instr.key: instr.value for instr in db_instructions}

    indentity_instructions = f"""
        Bạn là một chuyên gia tư vấn của một cửa hàng điện thoại, {identity}.
    """
    base_instructions = instructions_dict.get("base_instructions", "")

    product_workflow = instructions_dict.get("product_workflow", "")
    service_workflow = instructions_dict.get("service_workflow", "")
    accessory_workflow = instructions_dict.get("accessory_workflow", "")

    workflow_steps = []
    if True:
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
    workflow_instructions_add = instructions_dict.get("workflow_instructions", "")
    
    other_instructions = instructions_dict.get("other_instructions", "")

    final_system_prompt = "\n".join([
        indentity_instructions,
        base_instructions,
        workflow_instructions,
        workflow_instructions_add,
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
        mock_customer_config = Customer(
            customer_id="test_customer",
            ai_name="TestBot",
            ai_role="trợ lý ảo test",
            custom_prompt="Luôn trả lời bằng tiếng Việt.",
            service_feature_enabled=True,
            accessory_feature_enabled=False
        )
        # Cần mock session DB để test
        from database.database import SessionLocal
        db_session = SessionLocal()
        
        # Cần mock instructions trong DB để test
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
            # Upsert logic for testing
            existing = db_session.query(SystemInstruction).filter_by(key=instr.key).first()
            if existing:
                existing.value = instr.value
            else:
                db_session.add(instr)
        db_session.commit()

        # Mock Elasticsearch client for testing
        es_client = AsyncElasticsearch()

        agent_executor = create_agent_executor(
            es_client=es_client,
            db=db_session,
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