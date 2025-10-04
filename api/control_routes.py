from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.database import get_db, ChatThread, CustomerIsSale, ChatCustomer
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

# Customer-level bot control endpoints
@router.post("/customer/stop/{customer_id}")
async def stop_customer_bot(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Dừng hoạt động của bot cho toàn bộ customer_id.
    """
    chat_customer = db.query(ChatCustomer).filter(
        ChatCustomer.customer_id == customer_id
    ).first()
    
    if chat_customer:
        chat_customer.status = "stopped"
    else:
        chat_customer = ChatCustomer(
            customer_id=customer_id,
            status="stopped"
        )
        db.add(chat_customer)
    
    db.commit()
    return {"message": f"Bot đã được dừng cho customer_id {customer_id}."}

@router.post("/customer/start/{customer_id}")
async def start_customer_bot(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Khởi động lại hoạt động của bot cho toàn bộ customer_id.
    """
    chat_customer = db.query(ChatCustomer).filter(
        ChatCustomer.customer_id == customer_id
    ).first()
    
    if chat_customer:
        chat_customer.status = "active"
        db.commit()
    
    return {"message": f"Bot đã được khởi động cho customer_id {customer_id}."}

@router.get("/customer/status/{customer_id}")
async def get_customer_bot_status(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Lấy trạng thái hoạt động của bot cho toàn bộ customer_id.
    """
    chat_customer = db.query(ChatCustomer).filter(
        ChatCustomer.customer_id == customer_id
    ).first()
    
    status = chat_customer.status if chat_customer else "active"
    return {"customer_id": customer_id, "status": status}

@router.delete("/customer/{customer_id}")
async def delete_customer_data(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Xóa tất cả các bản ghi ChatCustomer của một khách hàng cụ thể.
    """
    try:
        # Đếm số lượng bản ghi ChatCustomer trước khi xóa
        chat_customer_count = db.query(ChatCustomer).filter(ChatCustomer.customer_id == customer_id).count()
        
        if chat_customer_count == 0:
            return {
                "message": f"Không có dữ liệu ChatCustomer nào để xóa cho khách hàng {customer_id}.",
                "deleted_count": 0
            }
        
        # Xóa tất cả bản ghi ChatCustomer của customer này
        deleted_count = db.query(ChatCustomer).filter(ChatCustomer.customer_id == customer_id).delete()
        
        db.commit()
        
        return {
            "message": f"Đã xóa thành công {deleted_count} bản ghi ChatCustomer cho khách hàng {customer_id}.",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi xóa dữ liệu ChatCustomer cho khách hàng {customer_id}: {str(e)}"
        )

@router.delete("/customer/threads/{customer_id}")
async def delete_all_customer_threads(
    customer_id: str,
    db: Session = Depends(get_db)
):
    """
    Xóa tất cả các bản ghi ChatThread của một khách hàng cụ thể.
    """
    try:
        # Đếm số lượng bản ghi ChatThread trước khi xóa
        chat_thread_count = db.query(ChatThread).filter(ChatThread.customer_id == customer_id).count()
        
        if chat_thread_count == 0:
            return {
                "message": f"Không có dữ liệu ChatThread nào để xóa cho khách hàng {customer_id}.",
                "deleted_count": 0
            }
        
        # Xóa tất cả bản ghi ChatThread của customer này
        deleted_count = db.query(ChatThread).filter(ChatThread.customer_id == customer_id).delete()
        
        db.commit()
        
        return {
            "message": f"Đã xóa thành công {deleted_count} bản ghi ChatThread cho khách hàng {customer_id}.",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi xóa dữ liệu ChatThread cho khách hàng {customer_id}: {str(e)}"
        )