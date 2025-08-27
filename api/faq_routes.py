from fastapi import APIRouter, Path, HTTPException, Depends
from typing import List
from dependencies import get_es_client
from elasticsearch import AsyncElasticsearch
from service.data.data_loader_elastic_search import (
    FAQ_INDEX,
    index_single_document,
    update_single_document,
    delete_single_document,
    delete_documents_by_customer
)
from service.models.schemas import FaqRow, FaqUpdate
from service.utils.helpers import sanitize_for_es

router = APIRouter()

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
                "size": 1000 
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
    faq_data: FaqRow,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """Thêm mới hoặc ghi đè một cặp FAQ."""
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        faq_dict = faq_data.model_dump()
        doc_id = faq_dict.get('faq_id')
        if not doc_id:
            raise HTTPException(status_code=400, detail="Thiếu 'faq_id' trong dữ liệu đầu vào.")
        
        response = await index_single_document(es_client, FAQ_INDEX, sanitized_customer_id, doc_id, faq_dict)
        return {"message": "FAQ đã được thêm/cập nhật thành công.", "result": response.body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/faq/{customer_id}/{faq_id}")
async def update_faq(
    customer_id: str,
    faq_id: str,
    faq_data: FaqUpdate,
    es_client: AsyncElasticsearch = Depends(get_es_client)
):
    """Cập nhật một cặp FAQ đã có."""
    if not es_client:
        raise HTTPException(status_code=503, detail="Không thể kết nối đến Elasticsearch.")
    try:
        sanitized_customer_id = sanitize_for_es(customer_id)
        faq_dict = faq_data.model_dump(exclude_unset=True)
        if not faq_dict:
            raise HTTPException(status_code=400, detail="Request body không được để trống.")
            
        response = await update_single_document(es_client, FAQ_INDEX, sanitized_customer_id, faq_id, faq_dict)
        return {"message": "FAQ đã được cập nhật thành công.", "result": response.body}
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
