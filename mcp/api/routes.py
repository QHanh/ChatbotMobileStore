"""Legacy file.

Routers for MCP configuration have been split into dedicated modules:
- mcp_server_routes.py: /config/mcp/servers...
- agent_binding_routes.py: /config/agents/... and effective config.

File này cung cấp một `router` gộp từ 2 module trên để giữ tương thích cũ
cho các import kiểu ``from mcp.api.routes import router``.

Đồng thời định nghĩa thêm endpoint `/chat-mcp/{threadId}` sử dụng orchestrator
ReAct + MCP mới.
"""

from fastapi import APIRouter, Path, HTTPException, Depends
from typing import List

from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

from service.models.schemas import ChatbotRequest
from database.database import get_db, ChatCustomer, ChatThread
from service.prompts.prompt_service import load_instructions
from api.chat_routes import _identify_product_from_image
from mcp.services import MCPClientManager
from mcp.models import EffectiveTenantConfig
from mcp.agents.orchestrator import run_orchestrator_react

from .mcp_server_routes import router as mcp_server_router
from .agent_binding_routes import router as agent_binding_router


router = APIRouter()
router.include_router(mcp_server_router)
router.include_router(agent_binding_router)

mcp_client_manager = MCPClientManager()


@router.post("/chat-mcp/{threadId}")
async def chat_mcp(
    request: ChatbotRequest,
    threadId: str = Path(..., description="Mã phiên chat với người dùng."),
    db: Session = Depends(get_db),
):
    """Endpoint chat dùng orchestrator ReAct + MCP.

    - Giữ nguyên kiểm tra trạng thái bot và xử lý ảnh như /chat.
    - Thay phần agent cũ bằng gọi run_orchestrator_react.
    """

    # Check customer-level bot status
    customer_status = db.query(ChatCustomer).filter(
        ChatCustomer.customer_id == request.customer_id
    ).first()
    if customer_status and customer_status.status == "stopped":
        raise HTTPException(
            status_code=403,
            detail="Bot đã bị dừng cho customer_id này.",
        )

    # Check thread-level bot status
    thread_status = db.query(ChatThread).filter(
        ChatThread.customer_id == request.customer_id,
        ChatThread.thread_id == threadId,
    ).first()
    if thread_status and thread_status.status == "stopped":
        raise HTTPException(
            status_code=403,
            detail="Bot đã bị dừng cho threadId của customer_id này.",
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
        image_urls = request.image_urls or []
        if image_url:
            image_urls = [*image_urls, image_url]
        image_base64 = request.image_base64

        print(f"[CHAT-MCP DEBUG] user_input: {user_input}")
        if request.history:
            print(f"[CHAT-MCP DEBUG] chat history (from API request): {request.history}")
        else:
            print("[CHAT-MCP DEBUG] chat history: empty or not provided")
        print(f"[CHAT-MCP DEBUG] image_urls: {image_urls}")
        print(f"[CHAT-MCP DEBUG] image_base64 length: {len(image_base64) if image_base64 else 0}")

        if not (user_input or image_urls or image_base64):
            raise HTTPException(status_code=400, detail="Bạn phải nhập câu hỏi hoặc gửi hình ảnh.")

        # Xử lý trường hợp có ảnh giống /chat
        if image_urls or image_base64:
            print(f"[CHAT-MCP DEBUG] Calling Product Identification with provider: {llm_provider}")
            product_info = await _identify_product_from_image(
                llm_provider, api_key, db, image_urls=image_urls, image_base64=image_base64
            )
            print(f"[CHAT-MCP DEBUG] Product identify result length: {len(product_info)}")
            print(f"[CHAT-MCP DEBUG] Product identify result: {product_info[:200] if product_info else 'EMPTY'}")
            instr = load_instructions(db)
            product_prefix_label = instr.get("product_prefix_label", "[Sản phẩm từ ảnh]:")
            if user_input and product_info:
                user_input = f"{user_input}\n\n{product_prefix_label}\n{product_info}"
                print("[CHAT-MCP DEBUG] Combined input (text + product info)")
            elif not user_input:
                user_input = product_info or ""
                print("[CHAT-MCP DEBUG] Using product-info-only input")
            if not user_input:
                raise HTTPException(status_code=400, detail="Không nhận diện được sản phẩm từ ảnh đã gửi.")

        print(f"[CHAT-MCP DEBUG] Final user_input length: {len(user_input)}")
        print(f"[CHAT-MCP DEBUG] Final user_input first 300 chars: {user_input[:300]}...")

        # Chuyển history (nếu có) sang danh sách BaseMessage cho orchestrator
        history_messages: List[BaseMessage] = []
        if request.history:
            for item in request.history:
                role = (item.role or "").lower()
                if role == "user":
                    history_messages.append(HumanMessage(content=item.message))
                elif role in ("assistant", "ai", "bot"):
                    history_messages.append(AIMessage(content=item.message))
                elif role == "system":
                    history_messages.append(SystemMessage(content=item.message))

        # Lấy cấu hình MCP effective cho tenant
        effective_config: EffectiveTenantConfig = mcp_client_manager.get_effective_config_for_tenant(
            db, customer_id
        )

        result = await run_orchestrator_react(
            db=db,
            tenant_id=customer_id,
            user_input=user_input,
            history=history_messages,
            access=access,
            api_key=api_key or "",
            effective_config=effective_config,
            mcp_client_manager=mcp_client_manager,
            thread_id=threadId,
        )

        return {"response": result.answer}

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"[CHAT-MCP ERROR] An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Đã có lỗi không mong muốn xảy ra từ server.")


__all__ = ["router", "mcp_server_router", "agent_binding_router"]
