from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from service.data.data_loader_vector_db import get_weaviate_client, process_and_load_text, process_and_load_file
from typing import Optional

router = APIRouter()

@router.post("/upload-document/{customer_id}")
async def upload_document(
    customer_id: str,
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Thêm dữ liệu văn bản hoặc tệp vào cơ sở dữ liệu vector của khách hàng.
    - Cung cấp `text` hoặc `file`, không phải cả hai.
    - Dữ liệu sẽ được thêm vào class `document_{customer_id}`.
    """
    if not text and not file:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp 'text' hoặc 'file'.")
    if text and file:
        raise HTTPException(status_code=400, detail="Chỉ cung cấp 'text' hoặc 'file', không phải cả hai.")

    client = get_weaviate_client()
    if not client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

    class_name = f"document_{customer_id}"

    try:
        if text:
            process_and_load_text(client, text, class_name)
            return {"message": f"Dữ liệu văn bản đã được thêm thành công vào '{class_name}'."}
        
        if file:
            content = await file.read()
            process_and_load_file(client, content, file.filename, class_name)
            return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm thành công vào '{class_name}'."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
