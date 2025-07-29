from fastapi import FastAPI, Path, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from service.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest
import uvicorn
from config.settings import APP_CONFIG, CORS_CONFIG

app = FastAPI(
    **APP_CONFIG
)

app.add_middleware(
    CORSMiddleware,
    **CORS_CONFIG
)

chat_memory = {}

agent_executor = create_agent_executor()

@app.post("/chat/{threadId}")
async def chat(
    request: ChatbotRequest,
    threadId: str = Path(..., description="The unique identifier for the chat thread.")
):

    if not threadId:
        raise HTTPException(status_code=400, detail="Thread ID is required.")

    try:
        user_input = request.query
        llm_provider = request.llm_provider
        
        if llm_provider:
            dynamic_agent_executor = create_agent_executor(llm_provider=llm_provider)
            response = invoke_agent_with_memory(dynamic_agent_executor, threadId, user_input, chat_memory)
        else:
            response = invoke_agent_with_memory(agent_executor, threadId, user_input, chat_memory)
        
        return {"response": response['output']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8010) 