from fastapi import APIRouter, Path, HTTPException, File, UploadFile, Depends
from typing import List
from dependencies import get_es_client
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import (
    process_and_index_data, 
    PRODUCTS_INDEX,
    index_single_document,
    delete_single_document,
    bulk_index_documents,
    process_and_upsert_file_data,
    delete_documents_by_customer,
    bulk_delete_documents
)
from service.models.schemas import ProductRow, BulkDeleteInput
from service.utils.helpers import sanitize_for_es

router = APIRouter()

PRODUCT_COLUMNS_CONFIG = {
    'names': [
        'Mã sản phẩm', 'Tên thiết bị', 'Màu sắc', 'Dung lượng', 'Bảo hành',
        'Tình trạng máy', 'Loại máy', 'Tình trạng pin', 'Giá bán lẻ', 'Giá bán buôn', 'Tồn kho', 'Ghi chú'
    ],
    'required': ['Mã sản phẩm', 'Tên thiết bị'],
    'id_field': 'Mã sản phẩm',
    'numerics': {
        'Tồn kho': int,
        'Giá bán lẻ': float,
        'Giá bán buôn': float,
        'Tình trạng pin': float
    },
    'rename_map': {
        "Mã sản phẩm": "ma_san_pham",
        "Tên thiết bị": "model",
        "Màu sắc": "mau_sac",
        "Dung lượng": "dung_luong",
        "Bảo hành": "bao_hanh",
        "Tình trạng máy": "tinh_trang_may",
        "Loại máy": "loai_thiet_bi",
        "Tình trạng pin": "tinh_trang_pin",
        "Giá bán lẻ": "gia",
        "Giá bán buôn": "gia_buon",
        "Tồn kho": "ton_kho",
        "Ghi chú": "ghi_chu"
    }
}

@router.post("/upload-product/{customer_id}")
async def upload_product_data(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu sản phẩm."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel dữ liệu sản phẩm cho một khách hàng.
    Hệ thống sẽ XÓA TẤT CẢ dữ liệu sản phẩm cũ của khách hàng này 
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
            index_name=PRODUCTS_INDEX,
            file_content=content,
            columns_config=PRODUCT_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu sản phẩm cho khách hàng '{customer_id}' đã được xử lý.",
            "index_name": PRODUCTS_INDEX,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")

@router.post("/insert-product-row/{customer_id}")
async def add_product(
    customer_id: str,
    product_data: ProductRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Thêm mới hoặc ghi đè một sản phẩm vào index chia sẻ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        product_dict = product_data.model_dump()
        doc_id = product_dict.get('ma_san_pham')
        if not doc_id:
            raise HTTPException(status_code=400, detail="Thiếu 'ma_san_pham' trong dữ liệu đầu vào.")
        
        response = await index_single_document(es_client, PRODUCTS_INDEX, sanitized_customer_id, doc_id, product_dict)
        return {"message": "Sản phẩm đã được thêm/cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/product/{customer_id}/{product_id}")
async def update_product(
    customer_id: str,
    product_id: str,
    product_data: ProductRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Cập nhật hoặc tạo mới thông tin cho một sản phẩm.
    Nếu sản phẩm chưa tồn tại, nó sẽ được tạo mới.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        product_dict = product_data.model_dump()

        body_product_id = product_dict.get('ma_san_pham')
        if body_product_id and body_product_id != product_id:
            raise HTTPException(
                status_code=400,
                detail=f"Mã sản phẩm trong URL ({product_id}) và trong body ({body_product_id}) không khớp."
            )
        
        product_dict['ma_san_pham'] = product_id
        
        response = await index_single_document(
            es_client, 
            PRODUCTS_INDEX, 
            sanitized_customer_id, 
            product_id, 
            product_dict
        )
        
        result_status = response.body.get('result')
        if result_status == 'created':
            message = "Sản phẩm đã được tạo mới thành công."
        elif result_status == 'updated':
            message = "Sản phẩm đã được cập nhật thành công."
        else:
            message = "Thao tác hoàn tất."

        return {"message": message, "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/product/{customer_id}/{product_id}")
async def delete_product(
    customer_id: str,
    product_id: str,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa một sản phẩm khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_single_document(es_client, PRODUCTS_INDEX, sanitized_customer_id, product_id)
        return {"message": "Sản phẩm đã được xóa thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/products/bulk/{customer_id}")
async def add_products_bulk(
    customer_id: str,
    products: List[ProductRow],
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Thêm mới hoặc cập nhật hàng loạt sản phẩm.
    Hàm này không xóa dữ liệu cũ.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        product_dicts = [p.model_dump() for p in products]
        success, failed = await bulk_index_documents(
            es_client, 
            PRODUCTS_INDEX, 
            sanitized_customer_id, 
            product_dicts, 
            id_field='ma_san_pham'
        )
        return {
            "message": "Thao tác hàng loạt hoàn tất.",
            "successfully_indexed": success,
            "failed_items": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-product/{customer_id}")
async def append_product_data_from_file(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu sản phẩm để nạp thêm."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel và nạp thêm (upsert) dữ liệu sản phẩm cho một khách hàng.
    Dữ liệu cũ sẽ không bị xóa. Nếu sản phẩm đã tồn tại, nó sẽ được cập nhật.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    try:
        content = await file.read()
        sanitized_customer_id = sanitize_for_es(customer_id)
        success, failed_items = await process_and_upsert_file_data(
            es_client=es_client,
            customer_id=sanitized_customer_id,
            index_name=PRODUCTS_INDEX,
            file_content=content,
            columns_config=PRODUCT_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu sản phẩm cho khách hàng '{customer_id}' đã được nạp thêm/cập nhật.",
            "successfully_indexed": success,
            "failed_items": failed_items
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")

@router.delete("/products/{customer_id}")
async def delete_all_products_by_customer(
    customer_id: str = Path(..., description="Mã khách hàng để xóa tất cả sản phẩm."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa TẤT CẢ các sản phẩm của một khách hàng khỏi index.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_documents_by_customer(
            es_client, 
            PRODUCTS_INDEX, 
            sanitized_customer_id
        )
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} sản phẩm cho khách hàng '{customer_id}'.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa sản phẩm: {e}")

@router.delete("/products/bulk/{customer_id}")
async def delete_products_bulk(
    customer_id: str,
    delete_input: BulkDeleteInput,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Xóa hàng loạt sản phẩm dựa trên danh sách ID.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await bulk_delete_documents(
            es_client,
            PRODUCTS_INDEX,
            sanitized_customer_id,
            delete_input.ids,
            id_field="ma_san_pham"
        )
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} sản phẩm.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa hàng loạt sản phẩm: {e}")
