from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.database import get_db, ChatThread
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class ThreadUpdate(BaseModel):
    thread_name: Optional[str] = None

@router.post("/stop/{customer_id}/{thread_id}")
async def stop_bot(
    customer_id: str,
    thread_id: str,
    request: ThreadUpdate,
    db: Session = Depends(get_db)
):
    """
    Dừng hoạt động của bot cho một phiên chat cụ thể.
    """
    thread = db.query(ChatThread).filter(
        ChatThread.customer_id == customer_id,
        ChatThread.thread_id == thread_id
    ).first()

    if thread:
        thread.status = "stopped"
        if request.thread_name:
            thread.thread_name = request.thread_name
    else:
        thread = ChatThread(
            customer_id=customer_id,
            thread_id=thread_id,
            status="stopped",
            thread_name=request.thread_name
        )
        db.add(thread)
    
    db.commit()
    return {"message": f"Bot has been stopped for thread {thread_id}."}

@router.post("/start/{customer_id}/{thread_id}")
async def start_bot(
    customer_id: str,
    thread_id: str,
    db: Session = Depends(get_db)
):
    """
    Khởi động lại hoạt động của bot cho một phiên chat cụ thể.
    """
    thread = db.query(ChatThread).filter(
        ChatThread.customer_id == customer_id,
        ChatThread.thread_id == thread_id
    ).first()

    if thread:
        thread.status = "active"
        db.commit()
    
    return {"message": f"Bot has been started for thread {thread_id}."}

@router.get("/status/{customer_id}/{thread_id}")
async def get_bot_status(
    customer_id: str,
    thread_id: str,
    db: Session = Depends(get_db)
):
    """
    Lấy trạng thái hoạt động của bot cho một phiên chat cụ thể.
    """
    thread = db.query(ChatThread).filter(
        ChatThread.customer_id == customer_id,
        ChatThread.thread_id == thread_id
    ).first()
    
    status = thread.status if thread else "active"
    return {"customer_id": customer_id, "thread_id": thread_id, "status": status}
