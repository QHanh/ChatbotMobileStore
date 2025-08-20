from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Query
from service.data.data_loader_vector_db import (
    get_weaviate_client, 
    process_and_load_text, 
    process_and_load_file, 
    ensure_document_collection_exists,
    ensure_tenant_exists,
    DOCUMENT_CLASS_NAME
)
from service.models.schemas import DocumentInput
from weaviate.classes.query import Filter
from typing import Optional
from service.utils.helpers import sanitize_for_weaviate

router = APIRouter()

def get_sanitized_tenant_id(customer_id: str) -> str:
    """Sử dụng hàm helper tập trung để làm sạch tenant ID."""
    return sanitize_for_weaviate(customer_id)

@router.post("/upload-text/{customer_id}")
async def upload_text(customer_id: str, doc_input: DocumentInput):
    client = None
    try:
        tenant_id = get_sanitized_tenant_id(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)
        
        source_name = doc_input.source if doc_input.source else doc_input.text[:20]
        process_and_load_text(client, doc_input.text, source_name, tenant_id)
        
        return {"message": f"Văn bản từ nguồn '{source_name}' đã được xử lý và thêm vào tenant '{tenant_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client: client.close()

@router.post("/upload-file/{customer_id}")
async def upload_file(customer_id: str, file: UploadFile = File(...), source: Optional[str] = Form(None)):
    client = None
    try:
        tenant_id = get_sanitized_tenant_id(customer_id)
        client = get_weaviate_client()
        ensure_document_collection_exists(client)
        ensure_tenant_exists(client, tenant_id)

        file_content = await file.read()
        source_name = source if source else file.filename
        
        process_and_load_file(client, file_content, source_name, file.filename, tenant_id)
        
        return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm vào tenant '{tenant_id}' với nguồn là '{source_name}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client: client.close()

@router.get("/documents/{customer_id}")
async def list_documents(customer_id: str, limit: int = 100, offset: int = 0):
    client = None
    try:
        tenant_id = get_sanitized_tenant_id(customer_id)
        client = get_weaviate_client()
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        
        if not collection.tenants.exists(tenant_id):
            return {"items": [], "count": 0}
            
        tenant_collection = collection.with_tenant(tenant_id)
        
        result = tenant_collection.query.fetch_objects(limit=limit, offset=offset, return_properties=["text", "source"])
        
        items = [{"id": obj.uuid, "text": obj.properties.get("text"), "source": obj.properties.get("source")} for obj in result.objects]
        return {"items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client: client.close()

@router.get("/sources/{customer_id}")
async def list_document_sources(customer_id: str):
    client = None
    try:
        tenant_id = get_sanitized_tenant_id(customer_id)
        client = get_weaviate_client()
        collection = client.collections.get(DOCUMENT_CLASS_NAME)

        if not collection.tenants.exists(tenant_id):
            return {"sources": []}
        
        tenant_collection = collection.with_tenant(tenant_id)
        result = tenant_collection.query.fetch_objects(return_properties=["source"])
        
        sources = sorted(list(set(obj.properties.get("source") for obj in result.objects if obj.properties and obj.properties.get("source"))))
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client: client.close()

@router.delete("/sources/{customer_id}")
async def delete_document_by_source(customer_id: str, source: str = Query(..., description="Tên 'source' của tài liệu cần xóa.")):
    client = None
    try:
        tenant_id = get_sanitized_tenant_id(customer_id)
        client = get_weaviate_client()
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        
        if not collection.tenants.exists(tenant_id):
            raise HTTPException(status_code=404, detail=f"Không tìm thấy tenant: {tenant_id}")
            
        tenant_collection = collection.with_tenant(tenant_id)
        result = tenant_collection.data.delete_many(where=Filter.by_property("source").equal(source))
        
        if result.failed > 0:
            raise HTTPException(status_code=500, detail=f"Xóa tài liệu thất bại với {result.failed} lỗi.")
        return {"message": f"Đã xóa thành công {result.successful} chunk của tài liệu '{source}' từ tenant '{tenant_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client: client.close()

@router.delete("/documents/{customer_id}")
async def delete_all_documents(customer_id: str):
    client = None
    try:
        tenant_id = get_sanitized_tenant_id(customer_id)
        client = get_weaviate_client()
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        
        if collection.tenants.exists(tenant_id):
            collection.tenants.remove(tenant_id)
            return {"message": f"Đã xóa thành công toàn bộ dữ liệu (tenant) của khách hàng '{customer_id}'."}
        else:
            return {"message": f"Không tìm thấy dữ liệu (tenant) của khách hàng '{customer_id}' để xóa."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client: client.close()