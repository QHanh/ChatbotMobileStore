from fastapi import APIRouter, Path, HTTPException, File, UploadFile, Depends
from typing import List
from dependencies import get_es_client
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import (
    process_and_index_data, 
    ACCESSORIES_INDEX,
    index_single_document,
    update_single_document,
    delete_single_document,
    bulk_index_documents,
    process_and_upsert_file_data
)
from service.models.schemas import AccessoryRow
from service.utils.helpers import sanitize_for_es
router = APIRouter()

ACCESSORY_COLUMNS_CONFIG = {
    'names': [
        'accessory_code', 'accessory_name', 'category', 'properties',
        'lifecare_price', 'trademark', 'guarantee', 'inventory',
        'specifications', 'avatar_images', 'link_accessory'
    ],
    'required': ['accessory_code', 'accessory_name'],
    'id_field': 'accessory_code',
    'numerics': {
        'inventory': int,
        'lifecare_price': float
    }
}

@router.post("/upload-accessory/{customer_id}")
async def upload_accessory_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu phụ kiện."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel dữ liệu phụ kiện cho một khách hàng.
    Hệ thống sẽ XÓA TẤT CẢ dữ liệu phụ kiện cũ của khách hàng này 
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
            index_name=ACCESSORIES_INDEX,
            file_content=content,
            columns_config=ACCESSORY_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu phụ kiện cho khách hàng '{customer_id}' đã được xử lý.",
            "index_name": ACCESSORIES_INDEX,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")

@router.post("/insert-accessory-row/{customer_id}")
async def add_accessory(
    customer_id: str,
    accessory_data: AccessoryRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Thêm mới hoặc ghi đè một phụ kiện vào index chia sẻ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        accessory_dict = accessory_data.model_dump()
        doc_id = accessory_dict.get('accessory_code')
        if not doc_id:
            raise HTTPException(status_code=400, detail="Thiếu 'accessory_code' trong dữ liệu đầu vào.")

        response = await index_single_document(es_client, ACCESSORIES_INDEX, sanitized_customer_id, doc_id, accessory_dict)
        return {"message": "Phụ kiện đã được thêm/cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/accessory/{customer_id}/{accessory_id}")
async def update_accessory(
    customer_id: str,
    accessory_id: str,
    accessory_data: AccessoryRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Cập nhật thông tin cho một phụ kiện đã có.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        accessory_dict = accessory_data.model_dump(exclude_unset=True)
        if 'accessory_code' in accessory_dict:
            del accessory_dict['accessory_code']
            
        response = await update_single_document(es_client, ACCESSORIES_INDEX, sanitized_customer_id, accessory_id, accessory_dict)
        return {"message": "Phụ kiện đã được cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/accessory/{customer_id}/{accessory_id}")
async def delete_accessory(
    customer_id: str,
    accessory_id: str,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa một phụ kiện khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_single_document(es_client, ACCESSORIES_INDEX, sanitized_customer_id, accessory_id)
        return {"message": "Phụ kiện đã được xóa thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/accessories/bulk/{customer_id}")
async def add_accessories_bulk(
    customer_id: str,
    accessories: List[AccessoryRow],
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Thêm mới hoặc cập nhật hàng loạt phụ kiện.
    Hàm này không xóa dữ liệu cũ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        accessory_dicts = [a.model_dump() for a in accessories]
        success, failed = await bulk_index_documents(
            es_client, 
            ACCESSORIES_INDEX, 
            sanitized_customer_id, 
            accessory_dicts, 
            id_field='accessory_code'
        )
        return {
            "message": "Thao tác hàng loạt hoàn tất.",
            "successfully_indexed": success,
            "failed_items": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-accessory/{customer_id}")
async def append_accessory_data_from_file(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu phụ kiện để nạp thêm."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel và nạp thêm (upsert) dữ liệu phụ kiện cho một khách hàng.
    Dữ liệu cũ sẽ không bị xóa. Nếu phụ kiện đã tồn tại, nó sẽ được cập nhật.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    try:
        content = await file.read()
        sanitized_customer_id = sanitize_for_es(customer_id)
        success, failed_items = await process_and_upsert_file_data(
            es_client=es_client,
            customer_id=sanitized_customer_id,
            index_name=ACCESSORIES_INDEX,
            file_content=content,
            columns_config=ACCESSORY_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu phụ kiện cho khách hàng '{customer_id}' đã được nạp thêm/cập nhật.",
            "successfully_indexed": success,
            "failed_items": failed_items
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")
