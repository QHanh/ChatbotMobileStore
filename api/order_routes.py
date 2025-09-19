from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from database.database import get_db, ProductOrder, ServiceOrder, AccessoryOrder

router = APIRouter()

# Response models
class BaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    order_id: str
    customer_id: str
    thread_id: str
    ten_khach_hang: str
    so_dien_thoai: str
    dia_chi: str
    loai_don_hang: str
    status: str
    created_at: datetime

class ProductOrderResponse(BaseOrderResponse):
    ma_san_pham: str
    ten_san_pham: str
    so_luong: int

class ServiceOrderResponse(BaseOrderResponse):
    ma_dich_vu: str
    ten_dich_vu: str
    loai_dich_vu: Optional[str] = None
    ten_san_pham_sua_chua: str

class AccessoryOrderResponse(BaseOrderResponse):
    ma_phu_kien: str
    ten_phu_kien: str
    so_luong: int

class AllOrdersResponse(BaseModel):
    customer_id: str
    total_orders: int
    product_orders: List[ProductOrderResponse]
    service_orders: List[ServiceOrderResponse]
    accessory_orders: List[AccessoryOrderResponse]

@router.get("/orders/{customer_id}", response_model=AllOrdersResponse)
async def get_all_orders_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng"),
    thread_id: Optional[str] = Query(None, description="Lọc theo thread_id (tùy chọn)"),
    limit: Optional[int] = Query(None, description="Giới hạn số lượng đơn hàng trả về"),
    offset: Optional[int] = Query(0, description="Bỏ qua số lượng đơn hàng"),
    db: Session = Depends(get_db)
):
    """
    Lấy tất cả đơn hàng của một customer_id.
    Có thể lọc theo thread_id và phân trang.
    """
    try:
        # Base queries
        product_query = db.query(ProductOrder).filter(ProductOrder.customer_id == customer_id)
        service_query = db.query(ServiceOrder).filter(ServiceOrder.customer_id == customer_id)
        accessory_query = db.query(AccessoryOrder).filter(AccessoryOrder.customer_id == customer_id)

        # Filter by thread_id if provided
        if thread_id:
            product_query = product_query.filter(ProductOrder.thread_id == thread_id)
            service_query = service_query.filter(ServiceOrder.thread_id == thread_id)
            accessory_query = accessory_query.filter(AccessoryOrder.thread_id == thread_id)

        # Order by created_at desc (newest first)
        product_query = product_query.order_by(ProductOrder.created_at.desc())
        service_query = service_query.order_by(ServiceOrder.created_at.desc())
        accessory_query = accessory_query.order_by(AccessoryOrder.created_at.desc())

        # Apply pagination if specified
        if limit:
            product_query = product_query.offset(offset).limit(limit)
            service_query = service_query.offset(offset).limit(limit)
            accessory_query = accessory_query.offset(offset).limit(limit)

        # Execute queries
        product_orders = product_query.all()
        service_orders = service_query.all()
        accessory_orders = accessory_query.all()

        # Calculate total orders
        total_orders = len(product_orders) + len(service_orders) + len(accessory_orders)

        # Convert to response models
        product_responses = [ProductOrderResponse.model_validate(order) for order in product_orders]
        service_responses = [ServiceOrderResponse.model_validate(order) for order in service_orders]
        accessory_responses = [AccessoryOrderResponse.model_validate(order) for order in accessory_orders]

        return AllOrdersResponse(
            customer_id=customer_id,
            total_orders=total_orders,
            product_orders=product_responses,
            service_orders=service_responses,
            accessory_orders=accessory_responses
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy đơn hàng: {str(e)}")

@router.get("/orders/{customer_id}/products", response_model=List[ProductOrderResponse])
async def get_product_orders_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng"),
    thread_id: Optional[str] = Query(None, description="Lọc theo thread_id (tùy chọn)"),
    limit: Optional[int] = Query(None, description="Giới hạn số lượng đơn hàng trả về"),
    offset: Optional[int] = Query(0, description="Bỏ qua số lượng đơn hàng"),
    db: Session = Depends(get_db)
):
    """
    Lấy tất cả đơn hàng sản phẩm của một customer_id.
    """
    try:
        query = db.query(ProductOrder).filter(ProductOrder.customer_id == customer_id)
        
        if thread_id:
            query = query.filter(ProductOrder.thread_id == thread_id)
        
        query = query.order_by(ProductOrder.created_at.desc())
        
        if limit:
            query = query.offset(offset).limit(limit)
        
        orders = query.all()
        
        if not orders:
            return []
        
        return [ProductOrderResponse.model_validate(order) for order in orders]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy đơn hàng sản phẩm: {str(e)}")

@router.get("/orders/{customer_id}/services", response_model=List[ServiceOrderResponse])
async def get_service_orders_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng"),
    thread_id: Optional[str] = Query(None, description="Lọc theo thread_id (tùy chọn)"),
    limit: Optional[int] = Query(None, description="Giới hạn số lượng đơn hàng trả về"),
    offset: Optional[int] = Query(0, description="Bỏ qua số lượng đơn hàng"),
    db: Session = Depends(get_db)
):
    """
    Lấy tất cả đơn hàng dịch vụ của một customer_id.
    """
    try:
        query = db.query(ServiceOrder).filter(ServiceOrder.customer_id == customer_id)
        
        if thread_id:
            query = query.filter(ServiceOrder.thread_id == thread_id)
        
        query = query.order_by(ServiceOrder.created_at.desc())
        
        if limit:
            query = query.offset(offset).limit(limit)
        
        orders = query.all()
        
        if not orders:
            return []
        
        return [ServiceOrderResponse.model_validate(order) for order in orders]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy đơn hàng dịch vụ: {str(e)}")

@router.get("/orders/{customer_id}/accessories", response_model=List[AccessoryOrderResponse])
async def get_accessory_orders_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng"),
    thread_id: Optional[str] = Query(None, description="Lọc theo thread_id (tùy chọn)"),
    limit: Optional[int] = Query(None, description="Giới hạn số lượng đơn hàng trả về"),
    offset: Optional[int] = Query(0, description="Bỏ qua số lượng đơn hàng"),
    db: Session = Depends(get_db)
):
    """
    Lấy tất cả đơn hàng phụ kiện của một customer_id.
    """
    try:
        query = db.query(AccessoryOrder).filter(AccessoryOrder.customer_id == customer_id)
        
        if thread_id:
            query = query.filter(AccessoryOrder.thread_id == thread_id)
        
        query = query.order_by(AccessoryOrder.created_at.desc())
        
        if limit:
            query = query.offset(offset).limit(limit)
        
        orders = query.all()
        
        if not orders:
            return []
        
        return [AccessoryOrderResponse.model_validate(order) for order in orders]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy đơn hàng phụ kiện: {str(e)}")

@router.get("/orders/{customer_id}/summary")
async def get_orders_summary_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng"),
    thread_id: Optional[str] = Query(None, description="Lọc theo thread_id (tùy chọn)"),
    db: Session = Depends(get_db)
):
    """
    Lấy tóm tắt đơn hàng của một customer_id (chỉ số lượng).
    """
    try:
        # Base queries for counting
        product_query = db.query(ProductOrder).filter(ProductOrder.customer_id == customer_id)
        service_query = db.query(ServiceOrder).filter(ServiceOrder.customer_id == customer_id)
        accessory_query = db.query(AccessoryOrder).filter(AccessoryOrder.customer_id == customer_id)

        # Filter by thread_id if provided
        if thread_id:
            product_query = product_query.filter(ProductOrder.thread_id == thread_id)
            service_query = service_query.filter(ServiceOrder.thread_id == thread_id)
            accessory_query = accessory_query.filter(AccessoryOrder.thread_id == thread_id)

        # Count orders
        product_count = product_query.count()
        service_count = service_query.count()
        accessory_count = accessory_query.count()
        total_count = product_count + service_count + accessory_count

        return {
            "customer_id": customer_id,
            "thread_id": thread_id,
            "total_orders": total_count,
            "product_orders_count": product_count,
            "service_orders_count": service_count,
            "accessory_orders_count": accessory_count
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy tóm tắt đơn hàng: {str(e)}")

# Request model for updating status
class UpdateStatusRequest(BaseModel):
    status: str = Field(description="Trạng thái mới của đơn hàng")

@router.put("/orders/{customer_id}/{thread_id}/{order_id}")
async def update_order_status(
    customer_id: str = Path(..., description="Mã khách hàng"),
    thread_id: str = Path(..., description="ID luồng chat"),
    order_id: str = Path(..., description="Mã đơn hàng"),
    request: UpdateStatusRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Cập nhật trạng thái của đơn hàng dựa theo customer_id, thread_id và order_id.
    """
    try:
        # Try to find the order in all three tables
        order = None
        order_type = None
        
        # Check ProductOrder first
        product_order = db.query(ProductOrder).filter(
            ProductOrder.customer_id == customer_id,
            ProductOrder.thread_id == thread_id,
            ProductOrder.order_id == order_id
        ).first()
        
        if product_order:
            order = product_order
            order_type = "product"
        else:
            # Check ServiceOrder
            service_order = db.query(ServiceOrder).filter(
                ServiceOrder.customer_id == customer_id,
                ServiceOrder.thread_id == thread_id,
                ServiceOrder.order_id == order_id
            ).first()
            
            if service_order:
                order = service_order
                order_type = "service"
            else:
                # Check AccessoryOrder
                accessory_order = db.query(AccessoryOrder).filter(
                    AccessoryOrder.customer_id == customer_id,
                    AccessoryOrder.thread_id == thread_id,
                    AccessoryOrder.order_id == order_id
                ).first()
                
                if accessory_order:
                    order = accessory_order
                    order_type = "accessory"
        
        if not order:
            raise HTTPException(
                status_code=404, 
                detail=f"Không tìm thấy đơn hàng với customer_id={customer_id}, thread_id={thread_id}, order_id={order_id}"
            )
        
        # Update status
        order.status = request.status
        db.commit()
        db.refresh(order)
        
        return {
            "message": "Cập nhật trạng thái thành công",
            "customer_id": customer_id,
            "thread_id": thread_id,
            "order_id": order_id,
            "order_type": order_type,
            "status": order.status,
            "updated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật trạng thái: {str(e)}")
