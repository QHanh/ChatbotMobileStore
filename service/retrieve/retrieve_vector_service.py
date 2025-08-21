import os
import weaviate
import asyncio
from typing import List, Dict, Any
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from service.data.data_loader_vector_db import DOCUMENT_CLASS_NAME
from dependencies import get_weaviate_client
from service.utils.helpers import sanitize_for_weaviate
from weaviate.classes.query import Filter

def _get_sanitized_tenant_id(customer_id: str) -> str:
    """Sử dụng hàm helper tập trung để làm sạch tenant ID."""
    return sanitize_for_weaviate(customer_id)

def _retrieve_documents_sync(query: str, tenant_id: str, query_vector: List[float], top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Hàm đồng bộ để truy xuất tài liệu từ một tenant cụ thể bằng Hybrid Search.
    """
    client = get_weaviate_client()
    if not client:
        return [{"error": "Không thể kết nối đến Weaviate."}]

    try:
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        
        if not collection.tenants.exists(tenant_id):
            return [{"message": f"Cơ sở tri thức cho khách hàng '{tenant_id}' chưa được tạo."}]

        tenant_collection = collection.with_tenant(tenant_id)
        
        try:
            response = tenant_collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=top_k,
                alpha=alpha,
                return_metadata=None,
                return_properties=["text", "source"]
            )
        except Exception as e:
            if "no such prop with name 'source'" in str(e):
                print("Warning: Thuộc tính 'source' không tồn tại. Fallback về chỉ lấy 'text'.")
                response = tenant_collection.query.hybrid(
                    query=query,
                    vector=query_vector,
                    limit=top_k,
                    alpha=alpha,
                    return_metadata=None,
                    return_properties=["text"]
                )
            else:
                raise e

        formatted_results = [
            {"content": obj.properties.get('text'), "metadata": {'source': obj.properties.get('source')}}
            for obj in response.objects
        ]
        
        print(f"Truy xuất lai ghép được {len(formatted_results)} tài liệu từ tenant '{tenant_id}'.")
        return formatted_results

    except Exception as e:
        print(f"Lỗi khi truy xuất tài liệu từ Weaviate: {e}")
        return [{"error": f"Lỗi truy xuất: {e}"}]
    finally:
        if client: client.close()

async def retrieve_documents(query: str, tenant_id: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Lớp vỏ (wrapper) bất đồng bộ cho hàm truy xuất tài liệu từ một tenant.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    query_vector = await embeddings.aembed_query(query)
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _retrieve_documents_sync, query, tenant_id, query_vector, top_k, alpha
    )
