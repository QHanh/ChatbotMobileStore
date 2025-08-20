from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Form
from service.data.data_loader_vector_db import get_weaviate_client, process_and_load_text, process_and_load_file, ensure_collection_exists
from service.models.schemas import DocumentInput
from fastapi import Query
from weaviate.classes.query import Filter
from typing import Optional

router = APIRouter()

@router.post("/upload-text/{customer_id}")
async def upload_text(
    customer_id: str,
    doc_input: DocumentInput
):
    """
    Tải lên và xử lý văn bản thô để thêm vào class `document_{customer_id}`.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")
        
        sanitized_customer_id = customer_id.replace("-", "_")
        class_name = f"document_{sanitized_customer_id}"
        ensure_collection_exists(client, class_name)
        
        source_name = doc_input.source if doc_input.source else doc_input.text[:5]
        process_and_load_text(client, doc_input.text, source_name, class_name)
        
        return {"message": f"Văn bản từ nguồn '{source_name}' đã được xử lý và thêm vào thành công."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()

@router.post("/upload-file/{customer_id}")
async def upload_file(
    customer_id: str,
    file: UploadFile = File(...),
    source: Optional[str] = Form(None)
):
    """
    Tải lên tệp (pdf, docx, txt), xử lý và thêm vào class `document_{customer_id}`.
    Có thể tùy chọn đặt tên 'source', nếu không sẽ dùng tên tệp.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")
        
        sanitized_customer_id = customer_id.replace("-", "_")
        class_name = f"document_{sanitized_customer_id}"
        ensure_collection_exists(client, class_name)

        file_content = await file.read()
        source_name = source if source else file.filename
        
        # Truyền cả source_name (để gán metadata) và file.filename (để xác định loại file)
        process_and_load_file(client, file_content, source_name, file.filename, class_name)
        
        return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm vào thành công với nguồn là '{source_name}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()


@router.get("/documents/{customer_id}")
async def list_documents(customer_id: str, limit: int = 100, offset: int = 0):
	"""
	Li tất cả các document tham vào class `document_{customer_id}`.
	Dùng tham số `limit` và `offset` để phân trang.
	"""
	client = None
	try:
		client = get_weaviate_client()
		if not client:
			raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

		sanitized_customer_id = customer_id.replace("-", "_")
		class_name_lower = f"document_{sanitized_customer_id}"
		class_name_upper = f"Document_{sanitized_customer_id}"
		if client.collections.exists(class_name_lower):
			class_name = class_name_lower
		elif client.collections.exists(class_name_upper):
			class_name = class_name_upper
		else:
			return {"items": [], "count": 0}

		collection = client.collections.get(class_name)

		return_props = ["text", "source"]
		try:
			result = collection.query.fetch_objects(
				limit=limit,
				offset=offset,
				return_properties=return_props
			)
		except Exception:
			result = collection.query.fetch_objects(
				limit=limit,
				offset=offset,
				return_properties=["text"]
			)

		objects = getattr(result, "objects", []) or []
		items = [
			{"id": obj.uuid, "text": (obj.properties or {}).get("text"), "source": (obj.properties or {}).get("source")}
			for obj in objects
		]
		return {"items": items, "count": len(items)}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))
	finally:
		if client:
			client.close()

@router.get("/sources/{customer_id}")
async def list_document_sources(customer_id: str):
    """
    Lấy danh sách các 'source' (tên file) duy nhất từ class `document_{customer_id}`.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

        sanitized_customer_id = customer_id.replace("-", "_")
        class_name = f"document_{sanitized_customer_id}"
        if not client.collections.exists(class_name):
            class_name = f"Document_{sanitized_customer_id}"
            if not client.collections.exists(class_name):
                return {"sources": []}

        collection = client.collections.get(class_name)
        
        result = collection.query.fetch_objects(return_properties=["source"])
        
        sources = sorted(list(set(
            obj.properties.get("source") 
            for obj in result.objects 
            if obj.properties and obj.properties.get("source")
        )))
        
        return {"sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()

@router.delete("/sources/{customer_id}")
async def delete_document_by_source(
    customer_id: str,
    source: str = Query(..., description="Tên 'source' (tên file) của tài liệu cần xóa.")
):
    """
    Xóa tất cả các chunk có cùng 'source' khỏi class `document_{customer_id}`.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

        sanitized_customer_id = customer_id.replace("-", "_")
        class_name = f"document_{sanitized_customer_id}"
        if not client.collections.exists(class_name):
            class_name = f"Document_{sanitized_customer_id}"
            if not client.collections.exists(class_name):
                raise HTTPException(status_code=404, detail=f"Không tìm thấy collection cho customer_id: {customer_id}")

        collection = client.collections.get(class_name)
        
        result = collection.data.delete_many(
            where=Filter.by_property("source").equal(source)
        )
        
        if result.failed > 0:
            raise HTTPException(status_code=500, detail=f"Xóa tài liệu thất bại với {result.failed} lỗi.")

        return {"message": f"Đã xóa thành công {result.successful} chunk của tài liệu '{source}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()

@router.delete("/documents/{customer_id}")
async def delete_all_documents(customer_id: str):
	"""
	Xóa tất cả dữ liệu cho khách hàng (xóa collection `document_{customer_id}`).
	"""
	client = None
	try:
		client = get_weaviate_client()
		if not client:
			raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")
        
		sanitized_customer_id = customer_id.replace("-", "_")
		class_name_lower = f"document_{sanitized_customer_id}"
		class_name_upper = f"Document_{sanitized_customer_id}"
        
		class_to_delete = None
		if client.collections.exists(class_name_lower):
			class_to_delete = class_name_lower
		elif client.collections.exists(class_name_upper):
			class_to_delete = class_name_upper

		if class_to_delete:
			client.collections.delete(class_to_delete)
			return {"message": f"Đã xóa tất cả dữ liệu của '{class_to_delete}'."}
		else:
			return {"message": f"Collection '{class_name_lower}' hoặc '{class_name_upper}' không tồn tại."}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))
	finally:
		if client:
			client.close()


@router.put("/replace-text/{customer_id}")
async def replace_text_documents(
    customer_id: str,
    document_input: DocumentInput = Body(...)
):
    """
    Xóa toàn bộ dữ liệu hiện có của khách hàng và nạp lại từ văn bản mới.
    - Thực hiện bằng cách xóa collection `document_{customer_id}` và tạo lại.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

        sanitized_customer_id = customer_id.replace("-", "_")
        class_name_lower = f"document_{sanitized_customer_id}"
        class_name_upper = f"Document_{sanitized_customer_id}"
        
        class_to_delete = None
        if client.collections.exists(class_name_lower):
            class_to_delete = class_name_lower
        elif client.collections.exists(class_name_upper):
            class_to_delete = class_name_upper

        if class_to_delete:
            client.collections.delete(class_to_delete)
        ensure_collection_exists(client, class_name_lower) # Use class_name_lower for ensure_collection_exists
        process_and_load_text(client, document_input.text, class_name_lower)
        return {"message": f"Đã thay thế toàn bộ dữ liệu cho '{class_name_lower}' bằng dữ liệu văn bản mới."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()


@router.put("/replace-file/{customer_id}")
async def replace_file_documents(
    customer_id: str,
    file: UploadFile = File(...)
):
    """
    Xóa toàn bộ dữ liệu hiện có của khách hàng và nạp lại từ nội dung tệp tải lên.
    - Thực hiện bằng cách xóa collection `document_{customer_id}` và tạo lại.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

        sanitized_customer_id = customer_id.replace("-", "_")
        class_name_lower = f"document_{sanitized_customer_id}"
        class_name_upper = f"Document_{sanitized_customer_id}"
        
        class_to_delete = None
        if client.collections.exists(class_name_lower):
            class_to_delete = class_name_lower
        elif client.collections.exists(class_name_upper):
            class_to_delete = class_name_upper

        if class_to_delete:
            client.collections.delete(class_to_delete)

        content = await file.read()
        ensure_collection_exists(client, class_name_lower) # Use class_name_lower for ensure_collection_exists
        process_and_load_file(client, content, file.filename, class_name_lower)
        return {"message": f"Đã thay thế toàn bộ dữ liệu cho '{class_name_lower}' bằng dữ liệu từ tệp '{file.filename}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()
