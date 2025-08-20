from fastapi import APIRouter, Path, HTTPException, File, UploadFile
from dependencies import es_client
from service.data.data_loader_elastic_search import (
    process_and_index_data, 
    ACCESSORIES_INDEX,
    index_single_document,
    update_single_document,
    delete_single_document
)
from service.models.schemas import AccessoryRow

router = APIRouter()

# Cấu hình cụ thể cho việc xử lý file phụ kiện
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

@router.post("/upload-accessories/{customer_id}")
async def upload_accessory_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu phụ kiện.")
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
        
        success, failed = await process_and_index_data(
            es_client=es_client,
            customer_id=customer_id,
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

@router.post("/accessories/{customer_id}")
async def add_accessory(
    customer_id: str,
    accessory_data: AccessoryRow
):
    """
    Thêm mới hoặc ghi đè một phụ kiện vào index chia sẻ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        accessory_dict = accessory_data.dict()
        doc_id = accessory_dict.pop('accessory_code')
        response = await index_single_document(es_client, ACCESSORIES_INDEX, customer_id, doc_id, accessory_dict)
        return {"message": "Phụ kiện đã được thêm/cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/accessories/{customer_id}/{accessory_id}")
async def update_accessory(
    customer_id: str,
    accessory_id: str,
    accessory_data: AccessoryRow
):
    """
    Cập nhật thông tin cho một phụ kiện đã có.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        accessory_dict = accessory_data.dict(exclude_unset=True)
        if 'accessory_code' in accessory_dict:
            del accessory_dict['accessory_code']
            
        response = await update_single_document(es_client, ACCESSORIES_INDEX, customer_id, accessory_id, accessory_dict)
        return {"message": "Phụ kiện đã được cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/accessories/{customer_id}/{accessory_id}")
async def delete_accessory(
    customer_id: str,
    accessory_id: str
):
    """
    Xóa một phụ kiện khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        response = await delete_single_document(es_client, ACCESSORIES_INDEX, customer_id, accessory_id)
        return {"message": "Phụ kiện đã được xóa thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
