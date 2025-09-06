from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.database import get_db, ChatThread, CustomerIsSale
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class IsSaleCustomerUpdate(BaseModel):
    is_sale_customer: bool

class ThreadUpdate(BaseModel):
    thread_name: Optional[str] = None

@router.get("/is_sale/{customer_id}/{thread_id}")
async def get_is_sale_customer_status(customer_id: str, thread_id: str, db: Session = Depends(get_db)):
    """
    Lấy trạng thái khách hàng buôn của một khách hàng cho một luồng chat cụ thể.
    """
    sale_status = db.query(CustomerIsSale).filter(
        CustomerIsSale.customer_id == customer_id,
        CustomerIsSale.thread_id == thread_id
    ).first()
    
    is_sale = sale_status.is_sale_customer if sale_status else False
    return {"customer_id": customer_id, "thread_id": thread_id, "is_sale_customer": is_sale}

@router.post("/is_sale/{customer_id}/{thread_id}")
async def update_is_sale_customer_status(customer_id: str, thread_id: str, update_data: IsSaleCustomerUpdate, db: Session = Depends(get_db)):
    """
    Cập nhật trạng thái khách hàng buôn cho một khách hàng trong một luồng chat cụ thể.
    """
    sale_status = db.query(CustomerIsSale).filter(
        CustomerIsSale.customer_id == customer_id,
        CustomerIsSale.thread_id == thread_id
    ).first()
    
    if not sale_status:
        sale_status = CustomerIsSale(
            customer_id=customer_id, 
            thread_id=thread_id, 
            is_sale_customer=update_data.is_sale_customer
        )
        db.add(sale_status)
    else:
        sale_status.is_sale_customer = update_data.is_sale_customer
        
    db.commit()
    db.refresh(sale_status)
    
    return {
        "message": f"Đã cập nhật trạng thái khách hàng buôn cho luồng {thread_id} của khách hàng {customer_id} thành {update_data.is_sale_customer}."
    }

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
