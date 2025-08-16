import os
import weaviate
import asyncio
from typing import List, Dict, Any

from service.data.data_loader_vector_db import get_weaviate_client

def _retrieve_documents_sync(query: str, class_name: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Hàm đồng bộ để truy xuất tài liệu từ Weaviate bằng tìm kiếm lai ghép (Hybrid Search) v4.
    alpha = 1: Tìm kiếm vector thuần túy.
    alpha = 0: Tìm kiếm từ khóa (BM25) thuần túy.
    """
    client = get_weaviate_client()
    if not client:
        return [{"error": "Không thể kết nối đến Weaviate."}]

    try:
        # Cú pháp kiểm tra collection tồn tại cho v4
        if not client.collections.exists(class_name):
            return [{"message": f"Cơ sở tri thức '{class_name}' chưa được tạo."}]

        # Lấy collection object
        collection = client.collections.get(class_name)

        # Cú pháp truy vấn hybrid search cho v4
        response = collection.query.hybrid(
            query=query,
            limit=top_k,
            alpha=alpha,
            return_metadata=None, # Tắt metadata mặc định để chỉ lấy properties
            return_properties=["text", "source"] # Chỉ định các thuộc tính cần lấy
        )
        
        formatted_results = [
            {
                "content": obj.properties.get('text'),
                "metadata": {'source': obj.properties.get('source')}
            }
            for obj in response.objects
        ]
        
        print(f"Truy xuất lai ghép v4 được {len(formatted_results)} tài liệu từ '{class_name}'.")
        return formatted_results

    except Exception as e:
        print(f"Lỗi khi truy xuất tài liệu từ Weaviate: {e}")
        return [{"error": f"Lỗi truy xuất: {e}"}]
    finally:
        # Client v4 yêu cầu đóng kết nối sau khi sử dụng
        if client:
            client.close()

async def retrieve_documents(query: str, class_name: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Lớp vỏ (wrapper) bất đồng bộ cho hàm truy xuất tài liệu.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _retrieve_documents_sync, query, class_name, top_k, alpha
    )
