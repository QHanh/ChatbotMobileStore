from fastapi import APIRouter, Path, HTTPException, File, UploadFile
from service.data.data_loader_elastic_search import (
    create_accessory_index, process_and_index_accessory_data,
    index_single_accessory, update_accessory_in_index, delete_accessory_from_index
)
from service.models.schemas import AccessoryRow
from dependencies import es_client

router = APIRouter()

@router.post("/upload-accessory/{customer_id}")
async def upload_accessory_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu phụ kiện.")
):
    """
    Tải lên file Excel cho khách hàng cụ thể, tạo index Elasticsearch riêng biệt,
    và đưa dữ liệu từ file vào index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    
    index_name = f"accessory_{customer_id}"
    
    if not es_client.indices.exists(index=index_name):
        create_accessory_index(es_client, index_name)
    try:
        file_content = await file.read()
        success, failed = process_and_index_accessory_data(es_client, index_name, file_content)
        return {
            "message": "Accessory data uploaded successfully.",
            "success": success,
            "failed": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-accessory-row/{customer_id}")
async def insert_accessory_row(
    customer_id: str,
    accessory_row: AccessoryRow
):
    """
    Thêm một phụ kiện vào index Elasticsearch đã chỉ định.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    
    index_name = f"accessory_{customer_id}"
    
    if not es_client.indices.exists(index=index_name):
        create_accessory_index(es_client, index_name)
    try:
        response = index_single_accessory(es_client, index_name, accessory_row.dict())
        return {
            "message": "Accessory row inserted successfully.",
            "document_id": response['_id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/accessory/{customer_id}/{accessory_id}")
async def delete_accessory(
    customer_id: str,
    accessory_id: str
):
    """
    Xóa một phụ kiện từ index Elasticsearch đã chỉ định.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    index_name = f"accessory_{customer_id}"
    try:
        delete_accessory_from_index(es_client, index_name, accessory_id)
        return {"message": "Accessory deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/accessory/{customer_id}/{accessory_id}")
async def update_accessory(
    customer_id: str,
    accessory_id: str,
    accessory_data: AccessoryRow
):
    """
    Cập nhật một phụ kiện trong index Elasticsearch đã chỉ định.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Elasticsearch is not available.")
    index_name = f"accessory_{customer_id}"
    try:
        update_accessory_in_index(es_client, index_name, accessory_id, accessory_data.dict())
        return {"message": "Accessory updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-accessory/{customer_id}")
async def insert_accessory_data(
    customer_id: str = Path(..., description="Mã khách hàng để thêm phụ kiện."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu phụ kiện mới để thêm vào.")
):
    """
    Thêm (insert/append) dữ liệu phụ kiện mới vào một index đã tồn tại cho khách hàng.
    Endpoint này sẽ không xóa dữ liệu cũ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    index_name = f"accessory_{customer_id}"

    if not es_client.indices.exists(index=index_name):
        raise HTTPException(status_code=404, detail=f"Index '{index_name}' không tồn tại. Vui lòng sử dụng endpoint /upload-accessory để tạo index trước.")

    try:
        content = await file.read()
        success, failed = process_and_index_accessory_data(es_client, index_name, content)
        
        return {
            "message": f"Dữ liệu phụ kiện mới cho khách hàng '{customer_id}' đã được thêm thành công.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
