import asyncio
from typing import List, Dict, Any
from service.data.data_loader_vector_db import DOCUMENT_CLASS_NAME, ensure_document_collection_exists
from dependencies import get_weaviate_client
from service.utils.helpers import sanitize_for_weaviate
import os
from google import genai
from google.genai import types

async def retrieve_documents(
    query: str, 
    customer_id: str, 
    top_k: int = 10, 
    alpha: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Truy xuất tài liệu từ một tenant cụ thể.
    """
    client = get_weaviate_client()
    tenant_id = sanitize_for_weaviate(customer_id)

    try:
        ensure_document_collection_exists(client)
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenants = collection.tenants.get()
        if tenant_id not in tenants:
            return [{"message": f"Cơ sở tri thức cho khách hàng '{tenant_id}' chưa được tạo."}]

        tenant_collection = collection.with_tenant(tenant_id)
        
        query_vector = None
        try:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            client = genai.Client(api_key=api_key) if api_key else genai.Client()
            embed_resp = await client.aio.models.embed_content(
                model="gemini-embedding-001",
                contents=query,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
            )
            if getattr(embed_resp, "embeddings", None):
                emb0 = embed_resp.embeddings[0]
                query_vector = getattr(emb0, "values", None) or getattr(emb0, "embedding", None)
        except Exception:
            query_vector = None

        if query_vector:
            response = tenant_collection.query.hybrid(
                query=query,
                vector=query_vector,
                limit=top_k,
                alpha=alpha,
                return_properties=["text", "source"]
            )
        else:
            response = tenant_collection.query.hybrid(
                query=query,
                limit=top_k,
                alpha=alpha,
                return_properties=["text", "source"]
            )

        formatted_results = [
            {
                "content": obj.properties.get('text'),
                "source": obj.properties.get('source')
            }
            for obj in response.objects
        ]
        
        print(f"Truy xuất hybrid được {len(formatted_results)} tài liệu từ tenant '{tenant_id}'.")
        return formatted_results

    except Exception as e:
        print(f"Lỗi khi truy xuất tài liệu từ Weaviate: {e}")
        return [{"error": f"Lỗi truy xuất: {e}"}]
    finally:
        # Do not close the shared Weaviate client here; it's managed by app lifespan
        pass
