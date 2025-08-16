from fastapi import APIRouter, Path, HTTPException, File, UploadFile
from service.data.data_loader_elastic_search import (
    create_product_index, process_and_index_product_data, 
    index_single_product, update_product_in_index, delete_product_from_index
)
from service.models.schemas import ProductRow
from dependencies import es_client

router = APIRouter()

@router.post("/upload-product/{customer_id}")
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
        
        content = await file.read()
        success, failed = process_and_index_product_data(es_client, index_name, content)
        
        return {
            "message": f"Dữ liệu sản phẩm cho khách hàng '{customer_id}' đã được xử lý.",
            "index_name": index_name,
            "successfully_indexed": success,
            "failed_to_index": failed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insert-product/{customer_id}")
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

@router.post("/insert-product-row/{customer_id}")
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
        create_product_index(es_client, index_name)

    try:
        response = index_single_product(es_client, index_name, product_row.dict())
        return {
            "message": "Product row inserted successfully.",
            "document_id": response['_id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/product/{customer_id}/{product_id}")
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

@router.delete("/product/{customer_id}/{product_id}")
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
