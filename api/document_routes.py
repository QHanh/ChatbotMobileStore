from fastapi import APIRouter, UploadFile, File, HTTPException, Body
from service.data.data_loader_vector_db import get_weaviate_client, process_and_load_text, process_and_load_file, ensure_collection_exists
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
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

        class_name = f"document_{customer_id}"
        ensure_collection_exists(client, class_name)
        process_and_load_text(client, document_input.text, class_name)
        return {"message": f"Dữ liệu văn bản đã được thêm thành công vào '{class_name}'."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()

@router.post("/upload-file/{customer_id}")
async def upload_file(
    customer_id: str,
    file: UploadFile = File(...)
):
    """
    Thêm dữ liệu từ một tệp vào cơ sở dữ liệu vector của khách hàng.
    - Dữ liệu sẽ được thêm vào class `document_{customer_id}`.
    """
    client = None
    try:
        client = get_weaviate_client()
        if not client:
            raise HTTPException(status_code=503, detail="Không thể kết nối đến Weaviate.")

        class_name = f"document_{customer_id}"
        
        content = await file.read()
        ensure_collection_exists(client, class_name)
        process_and_load_file(client, content, file.filename, class_name)
        return {"message": f"Tệp '{file.filename}' đã được xử lý và thêm thành công vào '{class_name}'."}
            
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

		# Ưu tiên class viết thường, fallback sang viết hoa nếu là dữ liệu cũ
		class_name_lower = f"document_{customer_id}"
		class_name_upper = f"Document_{customer_id}"
		if client.collections.exists(class_name_lower):
			class_name = class_name_lower
		elif client.collections.exists(class_name_upper):
			class_name = class_name_upper
		else:
			return {"items": [], "count": 0}

		collection = client.collections.get(class_name)

		# Cố gắng trả về cả 'text' và 'source'; nếu thiếu 'source' thì fallback về chỉ 'text'
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

		class_name = f"document_{customer_id}"
		if client.collections.exists(class_name):
			client.collections.delete(class_name)
			return {"message": f"Đã xóa tất cả dữ liệu của '{class_name}'."}
		else:
			return {"message": f"Collection '{class_name}' không tồn tại."}
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

        class_name = f"document_{customer_id}"
        # Xóa collection nếu tồn tại
        if client.collections.exists(class_name):
            client.collections.delete(class_name)
        # Tạo lại collection và nạp dữ liệu mới
        ensure_collection_exists(client, class_name)
        process_and_load_text(client, document_input.text, class_name)
        return {"message": f"Đã thay thế toàn bộ dữ liệu cho '{class_name}' bằng dữ liệu văn bản mới."}
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

        class_name = f"document_{customer_id}"
        # Xóa collection nếu tồn tại
        if client.collections.exists(class_name):
            client.collections.delete(class_name)

        # Đọc nội dung file và tạo lại collection rồi nạp dữ liệu
        content = await file.read()
        ensure_collection_exists(client, class_name)
        process_and_load_file(client, content, file.filename, class_name)
        return {"message": f"Đã thay thế toàn bộ dữ liệu cho '{class_name}' bằng dữ liệu từ tệp '{file.filename}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client:
            client.close()
