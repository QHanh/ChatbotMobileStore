from fastapi import APIRouter, HTTPException
from service.models.schemas import PersonaConfig, PromptConfig, ServiceFeatureConfig, AccessoryFeatureConfig
from dependencies import customer_configs

router = APIRouter()

@router.put("/config/persona/{customer_id}")
async def set_persona_config(
    customer_id: str,
    config: PersonaConfig
):
    """
    Cấu hình hoặc cập nhật vai trò và tên cho chatbot AI của khách hàng.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["persona"] = config.dict()
    return {"message": f"Vai trò và tên cho chatbot AI của khách hàng '{customer_id}' đã được cập nhật."}

@router.get("/config/persona/{customer_id}")
async def get_persona_config(customer_id: str):
    """
    Lấy cấu hình vai trò và tên của chatbot AI cho một khách hàng.
    """
    config = customer_configs.get(customer_id, {})
    persona = config.get("persona", {"ai_name": "Mai", "ai_role": "trợ lý ảo"})
    return persona

@router.delete("/config/persona/{customer_id}")
async def delete_persona_config(customer_id: str):
    """
    Xóa cấu hình vai trò và tên của chatbot AI, quay về mặc định.
    """
    if customer_id in customer_configs and "persona" in customer_configs[customer_id]:
        del customer_configs[customer_id]["persona"]
        return {"message": f"Cấu hình vai trò của khách hàng '{customer_id}' đã được xóa."}
    raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình vai trò để xóa.")

@router.put("/config/prompt/{customer_id}")
async def set_prompt_config(
    customer_id: str,
    config: PromptConfig
):
    """
    Thêm hoặc cập nhật system prompt tùy chỉnh cho khách hàng.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["custom_prompt"] = config.custom_prompt
    return {"message": f"System prompt tùy chỉnh cho khách hàng '{customer_id}' đã được cập nhật."}

@router.get("/config/prompt/{customer_id}")
async def get_prompt_config(customer_id: str):
    """
    Lấy system prompt tùy chỉnh của một khách hàng.
    """
    config = customer_configs.get(customer_id, {})
    custom_prompt = config.get("custom_prompt", "")
    return {"custom_prompt": custom_prompt}

@router.delete("/config/prompt/{customer_id}")
async def delete_prompt_config(customer_id: str):
    """
    Xóa system prompt tùy chỉnh của một khách hàng.
    """
    if customer_id in customer_configs and "custom_prompt" in customer_configs[customer_id]:
        del customer_configs[customer_id]["custom_prompt"]
        return {"message": f"System prompt tùy chỉnh của khách hàng '{customer_id}' đã được xóa."}
    raise HTTPException(status_code=404, detail="Không tìm thấy system prompt tùy chỉnh để xóa.")

@router.put("/config/service-feature/{customer_id}")
async def set_service_feature_config(
    customer_id: str,
    config: ServiceFeatureConfig
):
    """
    Bật hoặc tắt chức năng tư vấn dịch vụ cho chatbot của khách hàng.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["service_feature_enabled"] = config.enabled
    status = "bật" if config.enabled else "tắt"
    return {"message": f"Chức năng tư vấn dịch vụ cho khách hàng '{customer_id}' đã được {status}."}

@router.get("/config/service-feature/{customer_id}")
async def get_service_feature_config(customer_id: str):
    """
    Lấy trạng thái bật/tắt chức năng tư vấn dịch vụ của một khách hàng.
    """
    config = customer_configs.get(customer_id, {})
    is_enabled = config.get("service_feature_enabled", True)
    return {"enabled": is_enabled}

@router.put("/config/accessory-feature/{customer_id}")
async def set_accessory_feature_config(
    customer_id: str,
    config: AccessoryFeatureConfig
):
    """
    Bật hoặc tắt chức năng tư vấn phụ kiện cho chatbot của khách hàng.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["accessory_feature_enabled"] = config.enabled
    status = "bật" if config.enabled else "tắt"
    return {"message": f"Chức năng tư vấn phụ kiện cho khách hàng '{customer_id}' đã được {status}."}

@router.get("/config/accessory-feature/{customer_id}")
async def get_accessory_feature_config(customer_id: str):
    """
    Lấy trạng thái bật/tắt chức năng tư vấn phụ kiện của một khách hàng.
    """
    config = customer_configs.get(customer_id, {})
    is_enabled = config.get("accessory_feature_enabled", True)
    return {"enabled": is_enabled}
