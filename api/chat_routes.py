from fastapi import APIRouter, Path, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from service.agents.agent_service import create_agent_executor, invoke_agent_with_memory, clear_chat_history_for_customer
from service.models.schemas import ChatbotRequest, ChatHistoryResponse
from database.database import get_db, Customer, ChatThread, ChatHistory, ChatCustomer
from elasticsearch import AsyncElasticsearch
from dependencies import get_es_client
from typing import List
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from service.prompts.prompt_service import compose_system_prompt, load_instructions

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
async def chat(
    request: ChatbotRequest,
    threadId: str = Path(..., description="Mã phiên chat với người dùng."),
    db: Session = Depends(get_db),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Endpoint chính để tương tác với chatbot.
    """
    # Check customer-level bot status first
    customer_status = db.query(ChatCustomer).filter(
        ChatCustomer.customer_id == request.customer_id
    ).first()
    
    if customer_status and customer_status.status == "stopped":
        raise HTTPException(
            status_code=403, 
            detail="Bot đã bị dừng cho customer_id này."
        )
    
    # Check thread-level bot status
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
        image_url = request.image_url
        image_urls = (request.image_urls or [])
        if image_url:
            image_urls = [*image_urls, image_url]
        image_base64 = request.image_base64

        print(f"[CHAT DEBUG] user_input: {user_input}")
        print(f"[CHAT DEBUG] chat history: {request.chat_history}")
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
            es_client=es_client,
            history_override=request.history
        )

        return {"response": response['output']}

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Đã có lỗi không mong muốn xảy ra từ server.")

@router.get("/chat/system-prompt/{threadId}")
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
