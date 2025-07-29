from fastapi import FastAPI, Path, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from service.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest, PersonaConfig, PromptConfig
from service.data_loader_service import create_customer_index, process_and_index_data
from elasticsearch import Elasticsearch
import uvicorn
import io
from config.settings import APP_CONFIG, CORS_CONFIG, ELASTIC_HOST

app = FastAPI(**APP_CONFIG)

app.add_middleware(CORSMiddleware, **CORS_CONFIG)

chat_memory = {}
customer_configs = {}

try:
    es_client = Elasticsearch(hosts=[ELASTIC_HOST])
    if not es_client.ping():
        raise ConnectionError("Could not connect to Elasticsearch.")
    print("Successfully connected to Elasticsearch.")
except ConnectionError as e:
    print(f"Elasticsearch connection error: {e}")
    es_client = None

@app.post("/upload/{customer_id}")
async def upload_data(
    customer_id: str = Path(..., description="The unique identifier for the customer."),
    file: UploadFile = File(..., description="The Excel file containing product data.")
):
    """
    Uploads an Excel file for a specific customer, creates a dedicated Elasticsearch index,
    and populates it with the data from the file.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    
    index_name = f"product_{customer_id}"
    
    try:
        create_customer_index(es_client, index_name)
        
        file_stream = io.BytesIO(await file.read())
        
        success, failed = process_and_index_data(es_client, index_name, file_stream)
        
        return {
            "message": f"Data for customer '{customer_id}' has been processed.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/persona/{customer_id}")
async def configure_persona(
    customer_id: str,
    config: PersonaConfig
):
    """
    Configures the AI's persona (name and role) for a specific customer.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["persona"] = config.dict()
    return {"message": f"Persona for customer '{customer_id}' has been updated."}

@app.post("/config/prompt/{customer_id}")
async def configure_prompt(
    customer_id: str,
    config: PromptConfig
):
    """
    Adds custom instructions to the system prompt for a specific customer.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["custom_prompt"] = config.custom_prompt
    return {"message": f"Custom prompt for customer '{customer_id}' has been updated."}

@app.post("/chat/{threadId}")
async def chat(
    request: ChatbotRequest,
    threadId: str = Path(..., description="The unique identifier for the chat session with an end-user.")
):
    """
    Handles a chat request from an end-user.
    - `threadId` tracks the conversation session.
    - `customer_id` from the request body determines which store's data to use.
    """
    if not threadId:
        raise HTTPException(status_code=400, detail="Thread ID is required.")

    try:
        user_input = request.query
        llm_provider = request.llm_provider
        customer_id = request.customer_id

        agent_executor = create_agent_executor(
            customer_id=customer_id,
            customer_configs=customer_configs,
            llm_provider=llm_provider
        )
        
        response = invoke_agent_with_memory(agent_executor, threadId, user_input, chat_memory)
        
        return {"response": response['output']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8010) 