import os
import weaviate
import asyncio
from typing import List, Dict, Any
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from service.data.data_loader_vector_db import get_weaviate_client

def _retrieve_documents_sync(query: str, class_name: str, query_vector: List[float], top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Hàm đồng bộ để truy xuất tài liệu từ Weaviate bằng tìm kiếm kết hợp (Hybrid Search).
    """
    client = get_weaviate_client()
    if not client:
        return [{"error": "Không thể kết nối đến Weaviate."}]

    try:
        raw_customer_id = class_name.split('_')[-1]
        customer_id = raw_customer_id.replace("-", "_")
        
        class_name_lower = f"document_{customer_id}"
        class_name_upper = f"Document_{customer_id}"

        final_class_name = None
        if client.collections.exists(class_name_lower):
            final_class_name = class_name_lower
        elif client.collections.exists(class_name_upper):
            final_class_name = class_name_upper
        else:
            return [{"message": f"Cơ sở tri thức cho ID khách hàng '{customer_id}' chưa được tạo."}]

        collection = client.collections.get(final_class_name)

        try:
            response = collection.query.hybrid(
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
                response = collection.query.hybrid(
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
            {
                "content": obj.properties.get('text'),
                "metadata": {'source': obj.properties.get('source')}
            }
            for obj in response.objects
        ]
        
        print(f"Truy xuất lai ghép được {len(formatted_results)} tài liệu từ '{final_class_name}'.")
        return formatted_results

    except Exception as e:
        print(f"Lỗi khi truy xuất tài liệu từ Weaviate: {e}")
        return [{"error": f"Lỗi truy xuất: {e}"}]
    finally:
        if client:
            client.close()

async def retrieve_documents(query: str, class_name: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Lớp vỏ (wrapper) bất đồng bộ cho hàm truy xuất tài liệu.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    query_vector = await embeddings.aembed_query(query)
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _retrieve_documents_sync, query, class_name, query_vector, top_k, alpha
    )
