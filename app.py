from fastapi import FastAPI, Path, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from service.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest, PersonaConfig, PromptConfig
from service.data_loader_service import create_product_index, process_and_index_product_data, create_service_index, process_and_index_service_data
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

@app.post("/upload-product/{customer_id}")
async def upload_product_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu sản phẩm.")
):
    """
    Tải lên file Excel cho khách hàng cụ thể, tạo index Elasticsearch riêng biệt,
    và đưa dữ liệu từ file vào index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    index_name = f"product_{customer_id}"
    
    try:
        create_product_index(es_client, index_name)
        
        file_stream = io.BytesIO(await file.read())
        
        success, failed = process_and_index_product_data(es_client, index_name, file_stream)
        
        return {
            "message": f"Dữ liệu sản phẩm cho khách hàng '{customer_id}' đã được xử lý.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-service/{customer_id}")
async def upload_service_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu dịch vụ.")
):
    """
    Tải lên file Excel cho khách hàng cụ thể, tạo index Elasticsearch riêng biệt,
    và đưa dữ liệu từ file vào index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    index_name = f"service_{customer_id}"
    
    try:
        create_service_index(es_client, index_name)
        
        file_stream = io.BytesIO(await file.read())
        
        success, failed = process_and_index_service_data(es_client, index_name, file_stream)
        
        return {
            "message": f"Dữ liệu dịch vụ cho khách hàng '{customer_id}' đã được xử lý.",
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
    Cấu hình vai trò và tên cho chatbot AI cho khách hàng.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["persona"] = config.dict()
    return {"message": f"Vai trò và tên cho chatbot AI của khách hàng '{customer_id}' đã được cập nhật."}

@app.post("/config/prompt/{customer_id}")
async def configure_prompt(
    customer_id: str,
    config: PromptConfig
):
    """
    Thêm system prompt tùy chỉnh vào hệ thống prompt cho khách hàng.
    """
    if customer_id not in customer_configs:
        customer_configs[customer_id] = {}
    customer_configs[customer_id]["custom_prompt"] = config.custom_prompt
    return {"message": f"System prompt tùy chỉnh cho khách hàng '{customer_id}' đã được cập nhật."}

@app.post("/chat/{threadId}")
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