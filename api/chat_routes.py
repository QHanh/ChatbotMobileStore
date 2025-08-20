from fastapi import APIRouter, Path, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from service.agents.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest
from database.database import get_db, Customer
from dependencies import chat_memory
from elasticsearch import AsyncElasticsearch
from dependencies import get_es_client

router = APIRouter()

@router.post("/chat/{threadId}")
async def chat(
    request: ChatbotRequest,
    threadId: str = Path(..., description="Mã phiên chat với người dùng."),
    db: Session = Depends(get_db),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Endpoint chính để tương tác với chatbot.
    """
    if not threadId:
        raise HTTPException(status_code=400, detail="Mã phiên chat là bắt buộc.")

    try:
        user_input = request.query
        llm_provider = request.llm_provider
        customer_id = request.customer_id
        api_key = request.api_key

        customer_config = db.query(Customer).filter(Customer.customer_id == customer_id).first()
        if not customer_config:
            customer_config = Customer() 
        agent_executor = create_agent_executor(
            es_client=es_client,
            db=db,
            customer_id=customer_id,
            customer_config=customer_config,
            llm_provider=llm_provider,
            api_key=api_key
        )

        response = await invoke_agent_with_memory(agent_executor, threadId, user_input, chat_memory)

        return {"response": response['output']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
