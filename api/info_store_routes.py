from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from service.models.schemas import StoreInfo, StoreInfoUpdate
from database.database import get_db, StoreInfo as StoreInfoModel

router = APIRouter()

def get_or_create_store_info(db: Session, customer_id: str) -> StoreInfoModel:
    """
    Lấy thông tin cửa hàng từ DB, nếu chưa có thì tạo mới với giá trị mặc định.
    """
    store_info = db.query(StoreInfoModel).filter(StoreInfoModel.customer_id == customer_id).first()
    if not store_info:
        store_info = StoreInfoModel(customer_id=customer_id)
        db.add(store_info)
        db.commit()
        db.refresh(store_info)
    return store_info

@router.get("/store-info/{customer_id}", response_model=StoreInfo)
async def get_store_info(customer_id: str, db: Session = Depends(get_db)):
    """
    Lấy thông tin cửa hàng của một khách hàng.
    """
    try:
        store_info = get_or_create_store_info(db, customer_id)
        return store_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy thông tin cửa hàng: {str(e)}")

@router.put("/store-info/{customer_id}")
async def update_store_info(
    customer_id: str,
    store_info_update: StoreInfoUpdate,
    db: Session = Depends(get_db)
):
    """
    Cập nhật thông tin cửa hàng của một khách hàng.
    """
    try:
        store_info = get_or_create_store_info(db, customer_id)
        
        # Cập nhật các trường có giá trị
        update_data = store_info_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(store_info, field, value)
        
        db.commit()
        db.refresh(store_info)
        
        return {
            "message": f"Thông tin cửa hàng của khách hàng '{customer_id}' đã được cập nhật.",
            "store_info": store_info
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật thông tin cửa hàng: {str(e)}")

@router.delete("/store-info/{customer_id}")
async def delete_store_info(customer_id: str, db: Session = Depends(get_db)):
    """
    Xóa thông tin cửa hàng của một khách hàng (reset về mặc định).
    """
    try:
        store_info = db.query(StoreInfoModel).filter(StoreInfoModel.customer_id == customer_id).first()
        if store_info:
            # Reset tất cả các trường về None
            store_info.store_name = None
            store_info.store_address = None
            store_info.store_phone = None
            store_info.store_email = None
            store_info.store_website = None
            store_info.store_facebook = None
            store_info.store_address_map = None
            store_info.store_image_url = None
            
            db.commit()
            return {"message": f"Thông tin cửa hàng của khách hàng '{customer_id}' đã được reset về mặc định."}
        else:
            return {"message": f"Không tìm thấy thông tin cửa hàng cho khách hàng '{customer_id}'."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa thông tin cửa hàng: {str(e)}")
