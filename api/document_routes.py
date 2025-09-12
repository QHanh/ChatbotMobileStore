from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Query, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from io import BytesIO

from service.data.data_loader_vector_db import (
    get_weaviate_client, 
    process_and_load_text, 
    process_and_load_file, 
    ensure_document_collection_exists,
    ensure_tenant_exists,
    DOCUMENT_CLASS_NAME
)
from service.models.schemas import DocumentInput
from database.database import get_db, Document
from weaviate.classes.query import Filter
from typing import Optional
from service.utils.helpers import sanitize_for_weaviate

router = APIRouter()

@router.post("/upload-text/{customer_id}")
async def upload_text(customer_id: str, doc_input: DocumentInput, db: Session = Depends(get_db)):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)
        
        source_name = doc_input.source if doc_input.source else doc_input.text[:20]

        # Lưu nội dung gốc vào PostgreSQL
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            full_content=doc_input.text,
            content_type="text/plain"
        )
        db.add(new_document)
        db.commit()

        process_and_load_text(client, doc_input.text, source_name, tenant_id)
        
        return {"message": f"Văn bản từ nguồn '{source_name}' đã được xử lý và thêm vào tenant '{tenant_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass

@router.post("/upload-file/{customer_id}")
async def upload_file(customer_id: str, file: UploadFile = File(...), source: Optional[str] = Form(None), db: Session = Depends(get_db)):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)

        file_content = await file.read()
        source_name = source if source else file.filename
        
        # Lưu file gốc vào PostgreSQL
        new_document = Document(
            customer_id=customer_id,
            source_name=source_name,
            file_name=file.filename,
            content_type=file.content_type,
            file_content=file_content
        )
        db.add(new_document)
        db.commit()

        process_and_load_file(client, file_content, source_name, file.filename, tenant_id)
        
        return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm vào tenant '{tenant_id}' với nguồn là '{source_name}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass

@router.get("/document-original/{customer_id}")
async def get_original_document(
    customer_id: str, 
    source: str = Query(..., description="Tên 'source' của tài liệu cần lấy."),
    db: Session = Depends(get_db)
):
    """
    Lấy lại nội dung gốc của một tài liệu (text hoặc file) đã được upload.
    """
    document = db.query(Document).filter(
        Document.customer_id == customer_id,
        Document.source_name == source
    ).order_by(Document.created_at.desc()).first()

    if not document:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu với source '{source}' cho khách hàng '{customer_id}'.")

    if document.file_content:
        # Trả về file
        return StreamingResponse(
            BytesIO(document.file_content),
            media_type=document.content_type,
            headers={"Content-Disposition": f"attachment; filename={document.file_name}"}
        )
    elif document.full_content:
        # Trả về text
        return JSONResponse(
            content={
                "customer_id": document.customer_id,
                "source_name": document.source_name,
                "content": document.full_content,
                "created_at": document.created_at.isoformat()
            }
        )
    else:
        raise HTTPException(status_code=404, detail="Tài liệu không có nội dung.")

@router.get("/documents/{customer_id}")
async def list_documents(customer_id: str, limit: int = 100, offset: int = 0):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            return {"items": [], "count": 0}
            
        tenant_collection = collection.with_tenant(tenant_id)
        
        # Bỏ return_properties để đảm bảo tất cả thuộc tính được trả về
        result = tenant_collection.query.fetch_objects(limit=limit, offset=offset)
        
        items = [{"id": obj.uuid, "text": obj.properties.get("text"), "source": obj.properties.get("source")} for obj in result.objects]
        return {"items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass

@router.get("/sources/{customer_id}")
async def list_document_sources(customer_id: str):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            return {"sources": []}
        
        tenant_collection = collection.with_tenant(tenant_id)
        
        # Bỏ return_properties để đảm bảo tất cả thuộc tính được trả về
        result = tenant_collection.query.fetch_objects()
        
        sources = sorted(list(set(obj.properties.get("source") for obj in result.objects if obj.properties and obj.properties.get("source"))))
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass

@router.delete("/sources/{customer_id}")
async def delete_document_by_source(customer_id: str, source: str = Query(..., description="Tên 'source' của tài liệu cần xóa.")):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy tenant: {tenant_id}")
            
        tenant_collection = collection.with_tenant(tenant_id)
        result = tenant_collection.data.delete_many(where=Filter.by_property("source").equal(source))
        
        if result.failed > 0:
            raise HTTPException(status_code=500, detail=f"Xóa tài liệu thất bại với {result.failed} lỗi.")
        return {"message": f"Đã xóa thành công {result.successful} chunk của tài liệu '{source}' từ tenant '{tenant_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass

@router.delete("/documents/{customer_id}")
async def delete_all_documents(customer_id: str, db: Session = Depends(get_db)):
    client = None
    try:
        tenant_id = sanitize_for_weaviate(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id in tenants:
            collection.tenants.remove([tenant_id])
            
        # Xóa cả trong PostgreSQL
        db.query(Document).filter(Document.customer_id == customer_id).delete()
        db.commit()
            
        return {"message": f"Đã xóa thành công toàn bộ dữ liệu (tenant và bản ghi DB) của khách hàng '{customer_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass