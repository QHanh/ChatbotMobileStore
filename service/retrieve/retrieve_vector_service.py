import asyncio
from typing import List, Dict, Any
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from service.data.data_loader_vector_db import DOCUMENT_CLASS_NAME, ensure_document_collection_exists
from dependencies import get_weaviate_client
from service.utils.helpers import sanitize_for_weaviate

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
        
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        query_vector = await embeddings.aembed_query(query)

        response = tenant_collection.query.hybrid(
            query=query,
            vector=query_vector,
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
