from fastapi import APIRouter, Path, HTTPException, Depends, File, UploadFile
from typing import List
from dependencies import get_es_client
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import (
    FAQ_INDEX,
    index_single_document,
    delete_single_document,
    delete_documents_by_customer,
    process_and_upsert_file_data
)
from service.models.schemas import FaqRow, FaqCreate
from service.utils.helpers import sanitize_for_es
import hashlib

router = APIRouter()
FAQ_COLUMNS_CONFIG = {
    'names': [
        'Mã FAQ', 'Câu hỏi', 'Câu trả lời'
    ],
    'required': ['Mã FAQ', 'Câu hỏi', 'Câu trả lời'],
    'id_field': 'Mã FAQ',
    'rename_map': {
        "Mã FAQ": "ma_faq",
        "Câu hỏi": "cau_hoi",
        "Câu trả lời": "cau_tra_loi",
    }
}

async def get_all_faqs_by_customer(es_client: AsyncElasticsearch, index_name: str, customer_id: str):
    """Lấy tất cả các document của một customer_id."""
    try:
        response = await es_client.search(
            index=index_name,
            body={
                "query": {
                    "term": {
                        "customer_id": customer_id
                    }
                },
                "size": 1000,
                "sort": [
                    {"created_at": {"order": "desc"}} 
                ] 
            },
            routing=customer_id
        )
        return [hit['_source'] for hit in response['hits']['hits']]
    except Exception as e:
        print(f"Lỗi khi lấy tất cả document cho customer '{customer_id}' từ index '{index_name}': {e}")
        return []

@router.get("/faqs/{customer_id}", response_model=List[FaqRow])
async def get_all_faqs(
    customer_id: str = Path(..., description="Mã khách hàng."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """Lấy tất cả các cặp FAQ của một khách hàng."""
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    sanitized_customer_id = sanitize_for_es(customer_id)
    faqs = await get_all_faqs_by_customer(es_client, FAQ_INDEX, sanitized_customer_id)
    return faqs

@router.post("/faq/{customer_id}")
async def add_faq(
    customer_id: str,
    faq_data: FaqCreate,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """Thêm mới một cặp FAQ. ID sẽ được tự động tạo."""
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        
        # Tự động tạo ID từ hash của câu hỏi để tránh trùng lặp
        question_str = faq_data.question.strip().lower()
        doc_id = hashlib.sha1(question_str.encode('utf-8')).hexdigest()

        faq_dict = faq_data.model_dump()
        faq_dict['faq_id'] = doc_id
        
        response = await index_single_document(es_client, FAQ_INDEX, sanitized_customer_id, doc_id, faq_dict)
        return {"message": "FAQ đã được thêm thành công.", "faq_id": doc_id, "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/faq/{customer_id}/{faq_id}")
async def update_faq(
    customer_id: str,
    faq_id: str,
    faq_data: FaqCreate,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Cập nhật hoặc tạo mới một cặp FAQ.
    Nếu FAQ chưa tồn tại, nó sẽ được tạo mới với ID được cung cấp.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        faq_dict = faq_data.model_dump()
        faq_dict['faq_id'] = faq_id
            
        response = await index_single_document(
            es_client, 
            FAQ_INDEX, 
            sanitized_customer_id, 
            faq_id, 
            faq_dict
        )

        result_status = response.body.get('result')
        if result_status == 'created':
            message = "FAQ đã được tạo mới thành công."
        elif result_status == 'updated':
            message = "FAQ đã được cập nhật thành công."
        else:
            message = "Thao tác hoàn tất."

        return {"message": message, "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/faq/{customer_id}/{faq_id}")
async def delete_faq(
    customer_id: str,
    faq_id: str,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """Xóa một cặp FAQ."""
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_single_document(es_client, FAQ_INDEX, sanitized_customer_id, faq_id)
        return {"message": "FAQ đã được xóa thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/faqs/{customer_id}")
async def delete_all_faqs(
    customer_id: str = Path(..., description="Mã khách hàng để xóa tất cả FAQs."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """Xóa TẤT CẢ các cặp FAQ của một khách hàng."""
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        response = await delete_documents_by_customer(es_client, FAQ_INDEX, sanitized_customer_id)
        deleted_count = response.get('deleted', 0)
        return {"message": f"Đã xóa thành công {deleted_count} FAQs cho khách hàng '{customer_id}'.", "details": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa FAQs: {e}")

@router.post("/insert-faq/{customer_id}")
async def append_faq_data_from_file(
    customer_id: str = Path(..., description="Mã khách hàng."),
    file: UploadFile = File(..., description="File Excel chứa dữ liệu FAQ để nạp thêm."),
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """
    Tải lên file Excel và nạp thêm (upsert) dữ liệu FAQ cho một khách hàng.
    Dữ liệu cũ sẽ không bị xóa. Nếu FAQ đã tồn tại, nó sẽ được cập nhật.
    """
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    
    try:
        content = await file.read()
        sanitized_customer_id = sanitize_for_es(customer_id)
        success, failed_items = await process_and_upsert_file_data(
            es_client=es_client,
            customer_id=sanitized_customer_id,
            index_name=FAQ_INDEX,
            file_content=content,
            columns_config=FAQ_COLUMNS_CONFIG
        )
        
        return {
            "message": f"Dữ liệu FAQ cho khách hàng '{customer_id}' đã được nạp thêm/cập nhật.",
            "successfully_indexed": success,
            "failed_items": failed_items
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")