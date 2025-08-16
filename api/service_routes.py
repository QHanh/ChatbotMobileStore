from fastapi import APIRouter, Path, HTTPException, File, UploadFile
from service.data.data_loader_elastic_search import (
    create_service_index, process_and_index_service_data,
    index_single_service, update_service_in_index, delete_service_from_index
)
from service.models.schemas import ServiceRow
from dependencies import es_client

router = APIRouter()

@router.post("/upload-service/{customer_id}")
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
        
        content = await file.read()
        success, failed = process_and_index_service_data(es_client, index_name, content)
        
        return {
            "message": f"Dữ liệu dịch vụ cho khách hàng '{customer_id}' đã được xử lý.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-service/{customer_id}")
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

@router.post("/insert-service-row/{customer_id}")
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
        create_service_index(es_client, index_name)
    try:
        response = index_single_service(es_client, index_name, service_row.dict())
        return {
            "message": "Service row inserted successfully.",
            "document_id": response['_id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/service/{customer_id}/{service_id}")
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

@router.delete("/service/{customer_id}/{service_id}")
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
