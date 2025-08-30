from fastapi import APIRouter, Path, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from service.agents.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest
from database.database import get_db, Customer, ChatThread
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
    thread_status = db.query(ChatThread).filter(
        ChatThread.customer_id == request.customer_id,
        ChatThread.thread_id == threadId
    ).first()

    if thread_status and thread_status.status == "stopped":
        raise HTTPException(
            status_code=403, 
            detail="Bot đã bị dừng cho threadId của customer_id này."
        )

    if not threadId:
        raise HTTPException(status_code=400, detail="Mã phiên chat là bắt buộc.")

    customer_id = request.customer_id
    if not customer_id:
        raise HTTPException(status_code=400, detail="Mã khách hàng là bắt buộc.")

    access = request.access
    if access == 0:
        raise HTTPException(status_code=403, detail="Bạn không có quyền sử dụng tính năng này.")

    try:
        user_input = request.query
        llm_provider = request.llm_provider
        
        api_key = request.api_key

        customer_config = db.query(Customer).filter(Customer.customer_id == customer_id).first()
        if not customer_config:
            customer_config = Customer()

        if access != 100:
            access_str = str(access)
            customer_config.product_feature_enabled = '1' in access_str
            customer_config.service_feature_enabled = '2' in access_str
            customer_config.accessory_feature_enabled = '3' in access_str
            
        agent_executor = create_agent_executor(
            es_client=es_client,
            db=db,
            customer_id=customer_id,
            customer_config=customer_config,
            llm_provider=llm_provider,
            api_key=api_key
        )

        response = await invoke_agent_with_memory(
            agent_executor, 
            customer_id,
            threadId, 
            user_input, 
            chat_memory,
            es_client=es_client
        )

        return {"response": response['output']}

    except ValueError as ve:
        raise HTTPException(status_code=500, detail=str(ve))
