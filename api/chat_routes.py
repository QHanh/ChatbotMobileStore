from fastapi import APIRouter, Path, HTTPException
from service.agents.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest
from dependencies import chat_memory, customer_configs

router = APIRouter()

@router.post("/chat/{threadId}")
async def chat(
    request: ChatbotRequest,
    threadId: str = Path(..., description="Mã phiên chat với người dùng.")
):
    """
    Xử lý yêu cầu chat từ người dùng.
    - `threadId` theo dõi phiên trò chuyện.
    - `customer_id` xác định dữ liệu cửa hàng nào được sử dụng.
    """
    if not threadId:
        raise HTTPException(status_code=400, detail="Mã phiên chat là bắt buộc.")

    try:
        user_input = request.query
        llm_provider = request.llm_provider
        customer_id = request.customer_id
        api_key = request.api_key

        agent_executor = create_agent_executor(
            customer_id=customer_id,
            customer_configs=customer_configs,
            llm_provider=llm_provider,
            api_key=api_key
        )
        
        response = await invoke_agent_with_memory(agent_executor, threadId, user_input, chat_memory)
        
        return {"response": response['output']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
