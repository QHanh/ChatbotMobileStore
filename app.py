from fastapi import FastAPI, Path, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from service.agent_service import create_agent_executor, invoke_agent_with_memory
from service.models.schemas import ChatbotRequest, PersonaConfig, PromptConfig, ProductRow, ServiceRow, ServiceFeatureConfig
from service.data_loader_service import (
    create_product_index, process_and_index_product_data, 
    create_service_index, process_and_index_service_data,
    index_single_product, index_single_service,
    update_product_in_index, delete_product_from_index,
    update_service_in_index, delete_service_from_index
)
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

@app.post("/insert-product/{customer_id}")
async def insert_product_data(
    customer_id: str = Path(..., description="Mã khách hàng để thêm sản phẩm."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu sản phẩm mới để thêm vào.")
):
    """
    Thêm (insert/append) dữ liệu sản phẩm mới vào một index đã tồn tại cho khách hàng.
    Endpoint này sẽ không xóa dữ liệu cũ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    index_name = f"product_{customer_id}"
    
    if not es_client.indices.exists(index=index_name):
        raise HTTPException(status_code=404, detail=f"Index '{index_name}' không tồn tại. Vui lòng sử dụng endpoint /upload-product để tạo index trước.")

    try:
        content = await file.read()
        success, failed = process_and_index_product_data(es_client, index_name, content)
        
        return {
            "message": f"Dữ liệu sản phẩm mới cho khách hàng '{customer_id}' đã được thêm thành công.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/insert-service/{customer_id}")
async def insert_service_data(
    customer_id: str = Path(..., description="Mã khách hàng để thêm dịch vụ."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu dịch vụ mới để thêm vào.")
):
    """
    Thêm (insert/append) dữ liệu dịch vụ mới vào một index đã tồn tại cho khách hàng.
    Endpoint này sẽ không xóa dữ liệu cũ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    index_name = f"service_{customer_id}"

    if not es_client.indices.exists(index=index_name):
        raise HTTPException(status_code=404, detail=f"Index '{index_name}' không tồn tại. Vui lòng sử dụng endpoint /upload-service để tạo index trước.")

    try:
        content = await file.read()
        success, failed = process_and_index_service_data(es_client, index_name, content)
        
        return {
            "message": f"Dữ liệu dịch vụ mới cho khách hàng '{customer_id}' đã được thêm thành công.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/insert-product-row/{customer_id}")
async def insert_product_row(
    customer_id: str,
    product_row: ProductRow
):
    """
    Inserts a single product row into the customer's product index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    
    index_name = f"product_{customer_id}"
    
    if not es_client.indices.exists(index=index_name):
        raise HTTPException(status_code=404, detail=f"Index '{index_name}' does not exist.")

    try:
        response = index_single_product(es_client, index_name, product_row.dict())
        return {
            "message": "Product row inserted successfully.",
            "document_id": response['_id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/insert-service-row/{customer_id}")
async def insert_service_row(
    customer_id: str,
    service_row: ServiceRow
):
    """
    Inserts a single service row into the customer's service index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    
    index_name = f"service_{customer_id}"
    
    if not es_client.indices.exists(index=index_name):
        raise HTTPException(status_code=404, detail=f"Index '{index_name}' does not exist.")

    try:
        response = index_single_service(es_client, index_name, service_row.dict())
        return {
            "message": "Service row inserted successfully.",
            "document_id": response['_id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/product/{customer_id}/{product_id}")
async def update_product(
    customer_id: str,
    product_id: str,
    product_data: ProductRow
):
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    index_name = f"product_{customer_id}"
    try:
        update_product_in_index(es_client, index_name, product_id, product_data.dict(exclude_unset=True))
        return {"message": "Product updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/product/{customer_id}/{product_id}")
async def delete_product(
    customer_id: str,
    product_id: str
):
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    index_name = f"product_{customer_id}"
    try:
        delete_product_from_index(es_client, index_name, product_id)
        return {"message": "Product deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/service/{customer_id}/{service_id}")
async def update_service(
    customer_id: str,
    service_id: str,
    service_data: ServiceRow
):
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    index_name = f"service_{customer_id}"
    try:
        update_service_in_index(es_client, index_name, service_id, service_data.dict(exclude_unset=True))
        return {"message": "Service updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/service/{customer_id}/{service_id}")
async def delete_service(
    customer_id: str,
    service_id: str
):
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    index_name = f"service_{customer_id}"
    try:
        delete_service_from_index(es_client, index_name, service_id)
        return {"message": "Service deleted successfully."}
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


@app.post("/config/service-feature/{customer_id}")
async def configure_service_feature(
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
    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=True)