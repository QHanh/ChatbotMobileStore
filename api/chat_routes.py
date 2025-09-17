from fastapi import APIRouter, Path, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from service.agents.agent_service import create_agent_executor, invoke_agent_with_memory, clear_chat_history_for_customer
from service.models.schemas import ChatbotRequest, ChatHistoryResponse
from database.database import get_db, Customer, ChatThread, ChatHistory
from elasticsearch import AsyncElasticsearch
from dependencies import get_es_client
from typing import List

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
            thread_id=threadId,
            llm_provider=llm_provider,
            api_key=api_key
        )

        response = await invoke_agent_with_memory(
            agent_executor, 
            customer_id,
            threadId, 
            user_input, 
            db,
            es_client=es_client
        )

        return {"response": response['output']}

    except ValueError as ve:
        raise HTTPException(status_code=500, detail=str(ve))

@router.get("/chat-history/{customer_id}/{thread_id}", response_model=List[ChatHistoryResponse])
async def get_chat_history(
    customer_id: str = Path(..., description="Mã khách hàng."),
    thread_id: str = Path(..., description="Mã phiên chat."),
    db: Session = Depends(get_db)
):
    """
    Lấy toàn bộ lịch sử chat của một thread_id của customer_id theo thứ tự mới nhất đến cũ nhất.
    """
    history = db.query(ChatHistory).filter(
        ChatHistory.customer_id == customer_id,
        ChatHistory.thread_id == thread_id
    ).order_by(ChatHistory.id.desc()).all()

    if not history:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử chat.")
        
    return history

@router.post("/chat-history-clear/{customer_id}")
async def clear_history(
    customer_id: str = Path(..., description="Mã khách hàng để xóa lịch sử chat."),
    db: Session = Depends(get_db)
):
    """
    Xóa toàn bộ lịch sử chat của một khách hàng.
    """
    try:
        result = clear_chat_history_for_customer(customer_id, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa lịch sử chat: {str(e)}")
