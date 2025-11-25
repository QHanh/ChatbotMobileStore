from fastapi import APIRouter, Path, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from service.agents.agent_service import (
    get_or_create_agent_executor,
    invoke_agent_with_memory,
    clear_chat_history_for_customer,
    reset_agent_executor,
    reset_all_agent_executors,
    get_agent_cache_info
)
from service.models.schemas import ChatbotRequest, ChatHistoryResponse
from database.database import get_db, Customer, ChatThread, ChatHistory, ChatCustomer
from elasticsearch import AsyncElasticsearch
from dependencies import get_es_client
from typing import List
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from service.prompts.prompt_service import compose_system_prompt, load_instructions
from app_logging.decorators import with_log_context
from datetime import datetime, timezone

router = APIRouter()

async def _ocr_image_to_text(llm_provider: str, api_key: str, db: Session, image_url: str = None, image_base64: str = None, image_urls: list[str] | None = None) -> str:
    """Extract text from one or multiple images using LLM vision capabilities."""
    image_urls = image_urls or []
    if image_url:
        image_urls = [*image_urls, image_url]
    if not (image_urls or image_base64):
        return ""
    if not api_key:
        raise ValueError("Bạn chưa thêm API key bên trang cấu hình.")

    try:
        if llm_provider == "google_genai":
            llm = init_chat_model(model="gemini-2.5-flash", model_provider="google_genai", api_key=api_key)
        elif llm_provider == "openai":
            llm = init_chat_model(model="gpt-4o-mini", model_provider="openai", api_key=api_key)
        else:
            raise ValueError(f"Không tìm thấy LLM provider: {llm_provider}")

        image_blocks = []
        for url in image_urls:
            if url:
                image_blocks.append({"type": "image_url", "image_url": {"url": url}})
        if image_base64 and not image_blocks:
            data_url = image_base64.strip()
            if not data_url.startswith("data:"):
                data_url = f"data:image/png;base64,{data_url}"
            image_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

        instr = load_instructions(db)
        ocr_text_instruction = instr.get(
            "ocr_instruction",
            "Hãy trích xuất (OCR) toàn bộ văn bản có trong ảnh này. Chỉ trả về văn bản được trích xuất, giữ nguyên định dạng và xuống dòng. Nếu không có văn bản nào trong ảnh, hãy trả về chuỗi rỗng."
        )

        message_content = [{"type": "text", "text": ocr_text_instruction}]
        message_content.extend(image_blocks)

        message = HumanMessage(content=message_content)
        resp = await llm.ainvoke([message])
        
        text = resp.content if hasattr(resp, 'content') else str(resp)
        extracted_text = text.strip()
        
        print(f"[OCR DEBUG] Extracted text length: {len(extracted_text)}")
        print(f"[OCR DEBUG] First 200 chars: {extracted_text[:200] if extracted_text else 'EMPTY'}")
        
        return extracted_text
        
    except Exception as e:
        print(f"[OCR ERROR] Failed to extract text from image: {str(e)}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Không thể trích xuất văn bản từ ảnh: {str(e)}")

async def _identify_product_from_image(llm_provider: str, api_key: str, db: Session, image_url: str = None, image_base64: str = None, image_urls: list[str] | None = None) -> str:
    image_urls = image_urls or []
    if image_url:
        image_urls = [*image_urls, image_url]
    if not (image_urls or image_base64):
        return ""
    if not api_key:
        raise ValueError("Bạn chưa thêm API key bên trang cấu hình.")

    try:
        if llm_provider == "google_genai":
            llm = init_chat_model(model="gemini-2.5-flash", model_provider="google_genai", api_key=api_key)
        elif llm_provider == "openai":
            llm = init_chat_model(model="gpt-4o-mini", model_provider="openai", api_key=api_key)
        else:
            raise ValueError(f"Không tìm thấy LLM provider: {llm_provider}")

        image_blocks = []
        for url in image_urls:
            if url:
                image_blocks.append({"type": "image_url", "image_url": {"url": url}})
        if image_base64 and not image_blocks:
            data_url = image_base64.strip()
            if not data_url.startswith("data:"):
                data_url = f"data:image/png;base64,{data_url}"
            image_blocks.append({"type": "image_url", "image_url": {"url": data_url}})

        instr = load_instructions(db)
        identify_instruction = instr.get(
            "product_identify_instruction",
            "Hãy quan sát ảnh và xác định đây là sản phẩm gì hoặc tài liệu gì. Trả lời ngắn gọn bằng tiếng Việt với: tên sản phẩm, nhãn hiệu, model/biến thể chính, màu sắc/dung lượng nếu thấy, và một câu mô tả ngắn. Nếu không chắc chắn, trả về 'Không xác định'."
        )

        message_content = [{"type": "text", "text": identify_instruction}]
        message_content.extend(image_blocks)

        message = HumanMessage(content=message_content)
        resp = await llm.ainvoke([message])
        text = resp.content if hasattr(resp, 'content') else str(resp)
        result = text.strip()

        print(f"[IMAGE DETECT DEBUG] Result length: {len(result)}")
        print(f"[IMAGE DETECT DEBUG] First 200 chars: {result[:200] if result else 'EMPTY'}")

        return result
    except Exception as e:
        print(f"[IMAGE DETECT ERROR] Failed to identify product from image: {str(e)}")
        import traceback
        traceback.print_exc()
        raise ValueError(f"Không thể nhận diện sản phẩm từ ảnh: {str(e)}")

@router.post("/chat/{threadId}")
@with_log_context(
    event_action="chatbot.chat",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
async def chat(
    request: ChatbotRequest,
    threadId: str = Path(..., description="Mã phiên chat với người dùng."),
    db: Session = Depends(get_db),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Endpoint chính để tương tác với chatbot.
    """
    start_time = datetime.now(timezone.utc)

    # Check customer-level bot status first
    customer_status = db.query(ChatCustomer).filter(
        ChatCustomer.customer_id == request.customer_id
    ).first()

    if customer_status and customer_status.status == "stopped":
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        exc = HTTPException(
            status_code=403,
            detail="Bot đã bị dừng cho customer_id này."
        )
        exc.log_context = {
            "chat.customer_id": request.customer_id,
            "chat.thread_id": threadId,
            "chat.access": request.access,
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.customer_stopped",
        }
        raise exc

    # Check thread-level bot status
    thread_status = db.query(ChatThread).filter(
        ChatThread.customer_id == request.customer_id,
        ChatThread.thread_id == threadId
    ).first()

    if thread_status and thread_status.status == "stopped":
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        exc = HTTPException(
            status_code=403,
            detail="Bot đã bị dừng cho threadId của customer_id này."
        )
        exc.log_context = {
            "chat.customer_id": request.customer_id,
            "chat.thread_id": threadId,
            "chat.access": request.access,
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.thread_stopped",
        }
        raise exc

    if not threadId:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        exc = HTTPException(status_code=400, detail="Mã phiên chat là bắt buộc.")
        exc.log_context = {
            "chat.customer_id": request.customer_id,
            "chat.thread_id": threadId,
            "chat.access": request.access,
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.validation.thread_id_missing",
        }
        raise exc

    customer_id = request.customer_id
    if not customer_id:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        exc = HTTPException(status_code=400, detail="Mã khách hàng là bắt buộc.")
        exc.log_context = {
            "chat.customer_id": customer_id,
            "chat.thread_id": threadId,
            "chat.access": request.access,
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.validation.customer_id_missing",
        }
        raise exc

    access = request.access
    if access == 0:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        exc = HTTPException(status_code=403, detail="Bạn không có quyền sử dụng tính năng này.")
        exc.log_context = {
            "chat.customer_id": customer_id,
            "chat.thread_id": threadId,
            "chat.access": access,
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.access_denied",
        }
        raise exc

    user_input = None
    llm_provider = None
    image_urls = []
    image_base64 = None

    try:
        user_input = request.query
        llm_provider = request.llm_provider
        
        api_key = request.api_key
        image_url = request.image_url
        image_urls = (request.image_urls or [])
        if image_url:
            image_urls = [*image_urls, image_url]
        image_base64 = request.image_base64

        print(f"[CHAT DEBUG] user_input: {user_input}")
        if request.history:
            print(f"[CHAT DEBUG] chat history (from API request): {request.history}")
        else:
            print("[CHAT DEBUG] chat history (auto-retrieve): will be fetched by backend")
        print(f"[CHAT DEBUG] image_urls: {image_urls}")
        print(f"[CHAT DEBUG] image_base64 length: {len(image_base64) if image_base64 else 0}")
        print(f"[CHAT DEBUG] image_base64 first 50 chars: {image_base64[:50] if image_base64 else 'None'}")

        if not (user_input or image_urls or image_base64):
            raise HTTPException(status_code=400, detail="Bạn phải nhập câu hỏi hoặc gửi hình ảnh.")

        if image_urls or image_base64:
            print(f"[CHAT DEBUG] Calling Product Identification with provider: {llm_provider}")
            product_info = await _identify_product_from_image(llm_provider, api_key, db, image_urls=image_urls, image_base64=image_base64)
            print(f"[CHAT DEBUG] Product identify result length: {len(product_info)}")
            print(f"[CHAT DEBUG] Product identify result: {product_info[:200] if product_info else 'EMPTY'}")
            instr = load_instructions(db)
            product_prefix_label = instr.get("product_prefix_label", "[Sản phẩm từ ảnh]:")
            if user_input and product_info:
                user_input = f"{user_input}\n\n{product_prefix_label}\n{product_info}"
                print(f"[CHAT DEBUG] Combined input (text + product info)")
            elif not user_input:
                user_input = product_info or ""
                print(f"[CHAT DEBUG] Using product-info-only input")
            if not user_input:
                raise HTTPException(status_code=400, detail="Không nhận diện được sản phẩm từ ảnh đã gửi.")
        
        print(f"[CHAT DEBUG] Final user_input length: {len(user_input)}")
        print(f"[CHAT DEBUG] Final user_input first 300 chars: {user_input[:300]}...")

        customer_config = db.query(Customer).filter(Customer.customer_id == customer_id).first()
        if not customer_config:
            customer_config = Customer()

        if access != 100:
            access_str = str(access)
            customer_config.product_feature_enabled = '1' in access_str
            customer_config.service_feature_enabled = '2' in access_str
            customer_config.accessory_feature_enabled = '3' in access_str
            
        agent_executor = get_or_create_agent_executor(
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
            es_client=es_client,
            history_override=request.history
        )

        return {"response": response['output']}

    except ValueError as ve:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        http_exc = HTTPException(status_code=400, detail=str(ve))
        http_exc.log_context = {
            "chat.customer_id": customer_id,
            "chat.thread_id": threadId,
            "chat.access": access,
            "chat.llm_provider": llm_provider,
            "chat.has_image": bool(image_urls or image_base64),
            "chat.has_history": bool(request.history),
            "chat.user_input_length": len(user_input or ""),
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.value_error",
        }
        raise http_exc
    except Exception as e:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        http_exc = HTTPException(
            status_code=500,
            detail="Đã có lỗi không mong muốn xảy ra từ server.",
        )
        http_exc.log_context = {
            "chat.customer_id": customer_id,
            "chat.thread_id": threadId,
            "chat.access": access,
            "chat.llm_provider": llm_provider,
            "chat.has_image": bool(image_urls or image_base64),
            "chat.has_history": bool(request.history),
            "chat.user_input_length": len(user_input or ""),
            "chat.duration_ms": duration_ms,
            "error.stage": "chat.unexpected",
            "error.original_type": e.__class__.__name__,
            "error.original_message": str(e)[:500],
        }
        raise http_exc from e

@router.get("/chat/system-prompt/{threadId}")
@with_log_context(
    event_action="chatbot.system_prompt.get",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
async def get_system_prompt(
    threadId: str = Path(..., description="Mã phiên chat với người dùng."),
    customer_id: str = None,
    access: int = 100,
    db: Session = Depends(get_db)
):
    if not threadId:
        raise HTTPException(status_code=400, detail="Mã phiên chat là bắt buộc.")
    if not customer_id:
        raise HTTPException(status_code=400, detail="Mã khách hàng là bắt buộc.")

    customer_config = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer_config:
        customer_config = Customer(customer_id=customer_id)

    if access != 100:
        access_str = str(access)
        customer_config.product_feature_enabled = '1' in access_str
        customer_config.service_feature_enabled = '2' in access_str
        customer_config.accessory_feature_enabled = '3' in access_str

    system_prompt = compose_system_prompt(
        db=db,
        customer_config=customer_config,
        product_feature_enabled=customer_config.product_feature_enabled,
        service_feature_enabled=customer_config.service_feature_enabled,
        accessory_feature_enabled=customer_config.accessory_feature_enabled,
    )

    return {"system_prompt": system_prompt}

@router.get("/chat-history/{customer_id}/{thread_id}", response_model=List[ChatHistoryResponse])
@with_log_context(
    event_action="chatbot.chat_history.get",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
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
@with_log_context(
    event_action="chatbot.chat_history.clear",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
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


# ==================== AGENT CACHE MANAGEMENT ENDPOINTS ====================

@router.post("/agent/reset/{customer_id}")
@with_log_context(
    event_action="chatbot.agent.reset",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
async def reset_customer_agent(
    customer_id: str = Path(..., description="Mã khách hàng cần reset agent.")
):
    """
    Reset agent executor cho một customer cụ thể.
    Agent sẽ được tạo lại từ đầu ở lần chat tiếp theo.
    
    Sử dụng khi:
    - Muốn làm mới trạng thái agent
    - Sau khi thay đổi cấu hình customer
    - Khi agent gặp lỗi cần khởi động lại
    """
    try:
        result = reset_agent_executor(customer_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi reset agent: {str(e)}")


@router.post("/agent/reset-all")
@with_log_context(
    event_action="chatbot.agent.reset_all",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
async def reset_all_agents():
    """
    Reset tất cả agent executor trong cache.
    Tất cả agent sẽ được tạo lại từ đầu ở lần chat tiếp theo.
    
    Sử dụng khi:
    - Cần làm mới toàn bộ hệ thống
    - Sau khi cập nhật system prompt chung
    - Khi cần giải phóng bộ nhớ
    """
    try:
        result = reset_all_agent_executors()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi reset tất cả agents: {str(e)}")


@router.get("/agent/cache-info")
@with_log_context(
    event_action="chatbot.agent.cache_info",
    event_category="chatbot",
    source_layer="controller",
    source_controller="chat_routes",
)
async def get_cache_info():
    """
    Lấy thông tin về trạng thái cache agent hiện tại.
    
    Trả về:
    - Số lượng agent đang được cache
    - Thông tin chi tiết từng agent (customer_id, provider, thời gian cache)
    """
    try:
        result = get_agent_cache_info()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy thông tin cache: {str(e)}")
