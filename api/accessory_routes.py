from fastapi import APIRouter, Path, HTTPException, File, UploadFile, Depends
from typing import List
from dependencies import get_es_client
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import (
    process_and_index_data, 
    ACCESSORIES_INDEX,
    index_single_document,
    delete_single_document,
    bulk_index_documents,
    process_and_upsert_file_data,
    delete_documents_by_customer,
    bulk_delete_documents
)
from service.models.schemas import AccessoryRow, BulkDeleteInput
from service.utils.helpers import sanitize_for_es
router = APIRouter()

ACCESSORY_COLUMNS_CONFIG = {
    'names': [
        'Mã sản phẩm', 'Tên sản phẩm', 'Danh mục', 'Thuộc tính', 'Giá bán lẻ',
        'Giá bán buôn', 'Thương hiệu', 'Bảo hành', 'Tồn kho', 'Mô tả',
        'Ảnh sản phẩm', 'Link sản phẩm'
    ],
    'required': ['Mã sản phẩm', 'Tên sản phẩm'],
    'id_field': 'Mã sản phẩm',
    'numerics': {
        'Tồn kho': int,
        'Giá bán lẻ': float,
        'Giá bán buôn': float
    },
    'rename_map': {
        'Mã sản phẩm': 'accessory_code',
        'Tên sản phẩm': 'accessory_name',
        'Danh mục': 'category',
        'Thuộc tính': 'properties',
        'Giá bán lẻ': 'lifecare_price',
        'Giá bán buôn': 'sale_price',
        'Thương hiệu': 'trademark',
        'Bảo hành': 'guarantee',
        'Tồn kho': 'inventory',
        'Mô tả': 'specifications',
        'Ảnh sản phẩm': 'avatar_images',
        'Link sản phẩm': 'link_accessory'
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
    Cập nhật hoặc tạo mới thông tin cho một phụ kiện.
    Nếu phụ kiện chưa tồn tại, nó sẽ được tạo mới.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        accessory_dict = accessory_data.model_dump()

        body_accessory_id = accessory_dict.get('accessory_code')
        if body_accessory_id and body_accessory_id != accessory_id:
            raise HTTPException(
                status_code=400,
                detail=f"Mã phụ kiện trong URL ({accessory_id}) và trong body ({body_accessory_id}) không khớp."
            )
        
        accessory_dict['accessory_code'] = accessory_id
        
        response = await index_single_document(
            es_client, 
            ACCESSORIES_INDEX, 
            sanitized_customer_id, 
            accessory_id, 
            accessory_dict
        )
        
        result_status = response.body.get('result')
        if result_status == 'created':
            message = "Phụ kiện đã được tạo mới thành công."
        elif result_status == 'updated':
            message = "Phụ kiện đã được cập nhật thành công."
        else:
            message = "Thao tác hoàn tất."

        return {"message": message, "result": response.body}
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

@router.delete("/accessories/{customer_id}")
async def delete_all_accessories_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng để xóa tất cả phụ kiện."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa TẤT CẢ các phụ kiện của một khách hàng khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_documents_by_customer(
            es_client, 
            ACCESSORIES_INDEX, 
            sanitized_customer_id
        )
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} phụ kiện cho khách hàng '{customer_id}'.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa phụ kiện: {e}")

@router.delete("/accessories/bulk/{customer_id}")
async def delete_accessories_bulk(
    customer_id: str,
    delete_input: BulkDeleteInput,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa hàng loạt phụ kiện dựa trên danh sách ID.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await bulk_delete_documents(
            es_client,
            ACCESSORIES_INDEX,
            sanitized_customer_id,
            delete_input.ids,
            id_field="accessory_code"
        )
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} phụ kiện.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa hàng loạt phụ kiện: {e}")
