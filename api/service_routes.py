from fastapi import APIRouter, Path, HTTPException, File, UploadFile
from dependencies import es_client
from service.data.data_loader_elastic_search import (
    process_and_index_data, 
    SERVICES_INDEX,
    index_single_document,
    update_single_document,
    delete_single_document
)
from service.models.schemas import ServiceRow

router = APIRouter()

# Cấu hình cụ thể cho việc xử lý file dịch vụ
SERVICE_COLUMNS_CONFIG = {
    'names': [
        'ma_dich_vu', 'ten_dich_vu', 'hang_san_pham', 'ten_san_pham', 
        'mau_sac_san_pham', 'loai_dich_vu', 'gia', 'bao_hanh', 'ghi_chu'
    ],
    'required': ['ma_dich_vu', 'ten_dich_vu'],
    'id_field': 'ma_dich_vu',
    'numerics': {
        'gia': float
    }
}

@router.post("/upload-services/{customer_id}")
async def upload_service_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu dịch vụ.")
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
        
        success, failed = await process_and_index_data(
            es_client=es_client,
            customer_id=customer_id,
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

@router.post("/services/{customer_id}")
async def add_service(
    customer_id: str,
    service_data: ServiceRow
):
    """
    Thêm mới hoặc ghi đè một dịch vụ vào index chia sẻ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        service_dict = service_data.dict()
        doc_id = service_dict.pop('ma_dich_vu')
        response = await index_single_document(es_client, SERVICES_INDEX, customer_id, doc_id, service_dict)
        return {"message": "Dịch vụ đã được thêm/cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/services/{customer_id}/{service_id}")
async def update_service(
    customer_id: str,
    service_id: str,
    service_data: ServiceRow
):
    """
    Cập nhật thông tin cho một dịch vụ đã có.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        service_dict = service_data.dict(exclude_unset=True)
        if 'ma_dich_vu' in service_dict:
            del service_dict['ma_dich_vu']
            
        response = await update_single_document(es_client, SERVICES_INDEX, customer_id, service_id, service_dict)
        return {"message": "Dịch vụ đã được cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/services/{customer_id}/{service_id}")
async def delete_service(
    customer_id: str,
    service_id: str
):
    """
    Xóa một dịch vụ khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        response = await delete_single_document(es_client, SERVICES_INDEX, customer_id, service_id)
        return {"message": "Dịch vụ đã được xóa thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
