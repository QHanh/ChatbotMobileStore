import os
import weaviate
import asyncio
from typing import List, Dict, Any

from service.data.data_loader_vector_db import get_weaviate_client

def _retrieve_documents_sync(query: str, class_name: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Hàm đồng bộ để truy xuất tài liệu từ Weaviate bằng tìm kiếm lai ghép (Hybrid Search).
    alpha = 1: Tìm kiếm vector thuần túy.
    alpha = 0: Tìm kiếm từ khóa (BM25) thuần túy.
    """
    client = get_weaviate_client()
    if not client:
        return [{"error": "Không thể kết nối đến Weaviate."}]

    if not client.schema.exists(class_name):
        return [{"message": f"Cơ sở tri thức '{class_name}' chưa được tạo."}]

    try:
        response = (
            client.query.get(class_name, ["text", "source"])
            .with_hybrid(
                query=query,
                alpha=alpha
            )
            .with_limit(top_k)
            .do()
        )
        
        results = response['data']['Get'][class_name]
        
        formatted_results = [
            {
                "content": item.get('text'),
                "metadata": {'source': item.get('source')}
            }
            for item in results
        ]
        
        print(f"Truy xuất lai ghép được {len(formatted_results)} tài liệu từ '{class_name}'.")
        return formatted_results

    except Exception as e:
        print(f"Lỗi khi truy xuất tài liệu từ Weaviate: {e}")
        return [{"error": f"Lỗi truy xuất: {e}"}]

async def retrieve_documents(query: str, class_name: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """
    Lớp vỏ (wrapper) bất đồng bộ cho hàm truy xuất tài liệu.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _retrieve_documents_sync, query, class_name, top_k, alpha
    )
