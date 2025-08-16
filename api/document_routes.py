from fastapi import APIRouter, UploadFile, File, HTTPException, Body
from service.data.data_loader_vector_db import get_weaviate_client, process_and_load_text, process_and_load_file
from service.models.schemas import DocumentInput

router = APIRouter()

@router.post("/upload-text/{customer_id}")
async def upload_text(
    customer_id: str,
    document_input: DocumentInput = Body(...)
):
    """
    Thêm dữ liệu văn bản thô vào cơ sở dữ liệu vector của khách hàng.
    - Dữ liệu sẽ được thêm vào class `document_{customer_id}`.
    """
    client = get_weaviate_client()
    if not client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

    class_name = f"document_{customer_id}"

    try:
        process_and_load_text(client, document_input.text, class_name)
        return {"message": f"Dữ liệu văn bản đã được thêm thành công vào '{class_name}'."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-file/{customer_id}")
async def upload_file(
    customer_id: str,
    file: UploadFile = File(...)
):
    """
    Thêm dữ liệu từ một tệp vào cơ sở dữ liệu vector của khách hàng.
    - Dữ liệu sẽ được thêm vào class `document_{customer_id}`.
    """
    client = get_weaviate_client()
    if not client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

    class_name = f"document_{customer_id}"

    try:
        content = await file.read()
        process_and_load_file(client, content, file.filename, class_name)
        return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm thành công vào '{class_name}'."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
