from fastapi import APIRouter, Path, HTTPException, File, UploadFile, Depends
from typing import List
from dependencies import get_es_client
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import (
    process_and_index_data, 
    SERVICES_INDEX,
    index_single_document,
    update_single_document,
    delete_single_document,
    bulk_index_documents,
    process_and_upsert_file_data,
    delete_documents_by_customer,
    bulk_delete_documents
)
from service.models.schemas import ServiceRow, BulkDeleteInput
from service.utils.helpers import sanitize_for_es
router = APIRouter()

SERVICE_COLUMNS_CONFIG = {
    'names': [
        'ma_dich_vu', 'ten_dich_vu', 'hang_san_pham', 'ten_san_pham', 
        'mau_sac_san_pham', 'loai_dich_vu', 'gia', 'gia_buon', 'bao_hanh', 'ghi_chu'
    ],
    'required': ['ma_dich_vu', 'ten_dich_vu'],
    'id_field': 'ma_dich_vu',
    'numerics': {
        'gia': float,
        'gia_buon': float
    }
}

@router.post("/upload-service/{customer_id}")
async def upload_service_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu dịch vụ."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel dữ liệu dịch vụ cho một khách hàng.
    Hệ thống sẽ XÓA TẤT CẢ dữ liệu dịch vụ cũ của khách hàng này 
    và nạp lại toàn bộ dữ liệu từ file mới.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    try:
        content = await file.read()
        sanitized_customer_id = sanitize_for_es(customer_id)
        success, failed = await process_and_index_data(
            es_client=es_client,
            customer_id=sanitized_customer_id,
            index_name=SERVICES_INDEX,
            file_content=content,
            columns_config=SERVICE_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu dịch vụ cho khách hàng '{customer_id}' đã được xử lý.",
            "index_name": SERVICES_INDEX,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")

@router.post("/insert-service-row/{customer_id}")
async def add_service(
    customer_id: str,
    service_data: ServiceRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Thêm mới hoặc ghi đè một dịch vụ vào index chia sẻ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        service_dict = service_data.model_dump()
        doc_id = service_dict.get('ma_dich_vu')
        if not doc_id:
            raise HTTPException(status_code=400, detail="Thiếu 'ma_dich_vu' trong dữ liệu đầu vào.")

        response = await index_single_document(es_client, SERVICES_INDEX, sanitized_customer_id, doc_id, service_dict)
        return {"message": "Dịch vụ đã được thêm/cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/service/{customer_id}/{service_id}")
async def update_service(
    customer_id: str,
    service_id: str,
    service_data: ServiceRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Cập nhật thông tin cho một dịch vụ đã có.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        service_dict = service_data.model_dump(exclude_unset=True)
        if 'ma_dich_vu' in service_dict:
            del service_dict['ma_dich_vu']
            
        response = await update_single_document(es_client, SERVICES_INDEX, sanitized_customer_id, service_id, service_dict)
        return {"message": "Dịch vụ đã được cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/service/{customer_id}/{service_id}")
async def delete_service(
    customer_id: str,
    service_id: str,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa một dịch vụ khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_single_document(es_client, SERVICES_INDEX, sanitized_customer_id, service_id)
        return {"message": "Dịch vụ đã được xóa thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/services/bulk/{customer_id}")
async def add_services_bulk(
    customer_id: str,
    services: List[ServiceRow],
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Thêm mới hoặc cập nhật hàng loạt dịch vụ.
    Hàm này không xóa dữ liệu cũ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        service_dicts = [s.model_dump() for s in services]
        success, failed = await bulk_index_documents(
            es_client, 
            SERVICES_INDEX, 
            sanitized_customer_id, 
            service_dicts, 
            id_field='ma_dich_vu'
        )
        return {
            "message": "Thao tác hàng loạt hoàn tất.",
            "successfully_indexed": success,
            "failed_items": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-service/{customer_id}")
async def append_service_data_from_file(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu dịch vụ để nạp thêm."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel và nạp thêm (upsert) dữ liệu dịch vụ cho một khách hàng.
    Dữ liệu cũ sẽ không bị xóa. Nếu dịch vụ đã tồn tại, nó sẽ được cập nhật.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    try:
        content = await file.read()
        sanitized_customer_id = sanitize_for_es(customer_id)
        success, failed_items = await process_and_upsert_file_data(
            es_client=es_client,
            customer_id=sanitized_customer_id,
            index_name=SERVICES_INDEX,
            file_content=content,
            columns_config=SERVICE_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu dịch vụ cho khách hàng '{customer_id}' đã được nạp thêm/cập nhật.",
            "successfully_indexed": success,
            "failed_items": failed_items
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")

@router.delete("/services/{customer_id}")
async def delete_all_services_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng để xóa tất cả dịch vụ."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa TẤT CẢ các dịch vụ của một khách hàng khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_documents_by_customer(
            es_client, 
            SERVICES_INDEX, 
            sanitized_customer_id
        )
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} dịch vụ cho khách hàng '{customer_id}'.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa dịch vụ: {e}")

@router.delete("/services/bulk/{customer_id}")
async def delete_services_bulk(
    customer_id: str,
    delete_input: BulkDeleteInput,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa hàng loạt dịch vụ dựa trên danh sách ID.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await bulk_delete_documents(
            es_client,
            SERVICES_INDEX,
            sanitized_customer_id,
            delete_input.ids,
            id_field="ma_dich_vu"
        )
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} dịch vụ.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa hàng loạt dịch vụ: {e}")
