from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.database import get_db, ChatThread, Customer
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class IsSaleCustomerUpdate(BaseModel):
    is_sale_customer: bool

class ThreadUpdate(BaseModel):
    thread_name: Optional[str] = None

@router.get("/is_sale/{customer_id}")
async def get_is_sale_customer_status(customer_id: str, db: Session = Depends(get_db)):
    """
    Lấy trạng thái khách hàng buôn của một khách hàng.
    """
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")
    return {"customer_id": customer_id, "is_sale_customer": customer.is_sale_customer}

@router.post("/is_sale/{customer_id}")
async def update_is_sale_customer_status(customer_id: str, update_data: IsSaleCustomerUpdate, db: Session = Depends(get_db)):
    """
    Cập nhật trạng thái khách hàng buôn cho một khách hàng.
    """
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        customer = Customer(customer_id=customer_id, is_sale_customer=update_data.is_sale_customer)
        db.add(customer)
    else:
        customer.is_sale_customer = update_data.is_sale_customer
    db.commit()
    return {"message": f"Đã cập nhật trạng thái khách hàng buôn cho {customer_id} thành {update_data.is_sale_customer}."}

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
