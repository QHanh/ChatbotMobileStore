from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from service.models.schemas import PersonaConfig, PromptConfig, ServiceFeatureConfig, AccessoryFeatureConfig
from database.database import get_db, Customer

router = APIRouter()

def get_or_create_customer(db: Session, customer_id: str) -> Customer:
    """
    Lấy thông tin khách hàng từ DB, nếu chưa có thì tạo mới với giá trị mặc định.
    """
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        customer = Customer(customer_id=customer_id)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    return customer

@router.put("/config/persona/{customer_id}")
async def set_persona_config(
    customer_id: str,
    config: PersonaConfig,
    db: Session = Depends(get_db)
):
    """
    Cấu hình hoặc cập nhật vai trò và tên cho chatbot AI của khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    customer.ai_name = config.ai_name
    customer.ai_role = config.ai_role
    db.commit()
    return {"message": f"Vai trò và tên cho chatbot AI của khách hàng '{customer_id}' đã được cập nhật."}

@router.get("/config/persona/{customer_id}")
async def get_persona_config(customer_id: str, db: Session = Depends(get_db)):
    """
    Lấy cấu hình vai trò và tên của chatbot AI cho một khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    return {"ai_name": customer.ai_name, "ai_role": customer.ai_role}

@router.delete("/config/persona/{customer_id}")
async def delete_persona_config(customer_id: str, db: Session = Depends(get_db)):
    """
    Xóa cấu hình vai trò và tên của chatbot AI, quay về mặc định.
    """
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if customer:
        customer.ai_name = "Mai"  # Default value
        customer.ai_role = "trợ lý ảo" # Default value
        db.commit()
        return {"message": f"Cấu hình vai trò của khách hàng '{customer_id}' đã được xóa về mặc định."}
    raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.")

@router.put("/config/prompt/{customer_id}")
async def set_prompt_config(
    customer_id: str,
    config: PromptConfig,
    db: Session = Depends(get_db)
):
    """
    Thêm hoặc cập nhật system prompt tùy chỉnh cho khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    customer.custom_prompt = config.custom_prompt
    db.commit()
    return {"message": f"System prompt tùy chỉnh cho khách hàng '{customer_id}' đã được cập nhật."}

@router.get("/config/prompt/{customer_id}")
async def get_prompt_config(customer_id: str, db: Session = Depends(get_db)):
    """
    Lấy system prompt tùy chỉnh của một khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    return {"custom_prompt": customer.custom_prompt or ""}

@router.delete("/config/prompt/{customer_id}")
async def delete_prompt_config(customer_id: str, db: Session = Depends(get_db)):
    """
    Xóa system prompt tùy chỉnh của một khách hàng.
    """
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if customer:
        customer.custom_prompt = None
        db.commit()
        return {"message": f"System prompt tùy chỉnh của khách hàng '{customer_id}' đã được xóa."}
    raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.")

@router.put("/config/service-feature/{customer_id}")
async def set_service_feature_config(
    customer_id: str,
    config: ServiceFeatureConfig,
    db: Session = Depends(get_db)
):
    """
    Bật hoặc tắt chức năng tư vấn dịch vụ cho chatbot của khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    customer.service_feature_enabled = config.enabled
    db.commit()
    status = "bật" if config.enabled else "tắt"
    return {"message": f"Chức năng tư vấn dịch vụ cho khách hàng '{customer_id}' đã được {status}."}

@router.get("/config/service-feature/{customer_id}")
async def get_service_feature_config(customer_id: str, db: Session = Depends(get_db)):
    """
    Lấy trạng thái bật/tắt chức năng tư vấn dịch vụ của một khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    return {"enabled": customer.service_feature_enabled}

@router.put("/config/accessory-feature/{customer_id}")
async def set_accessory_feature_config(
    customer_id: str,
    config: AccessoryFeatureConfig,
    db: Session = Depends(get_db)
):
    """
    Bật hoặc tắt chức năng tư vấn phụ kiện cho chatbot của khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    customer.accessory_feature_enabled = config.enabled
    db.commit()
    status = "bật" if config.enabled else "tắt"
    return {"message": f"Chức năng tư vấn phụ kiện cho khách hàng '{customer_id}' đã được {status}."}

@router.get("/config/accessory-feature/{customer_id}")
async def get_accessory_feature_config(customer_id: str, db: Session = Depends(get_db)):
    """
    Lấy trạng thái bật/tắt chức năng tư vấn phụ kiện của một khách hàng.
    """
    customer = get_or_create_customer(db, customer_id)
    return {"enabled": customer.accessory_feature_enabled}
