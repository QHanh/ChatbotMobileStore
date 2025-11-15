"""MCP server cho domain FAQ (câu hỏi thường gặp).

Wrap logic ``search_faqs`` hiện tại qua MCP.
"""

from typing import Any, Dict, Optional, List

from elasticsearch import AsyncElasticsearch
from config.settings import ELASTIC_HOST
from service.data.data_loader_elastic_search import FAQ_INDEX
from service.utils.helpers import sanitize_for_es
from mcp.server.fastmcp import FastMCP


mcp = FastMCP(name="faq-mcp")

_es_client: Optional[AsyncElasticsearch] = None


async def _get_es_client() -> AsyncElasticsearch:
    """Khởi tạo/lấy lại client Elasticsearch dùng chung cho MCP server FAQ."""

    global _es_client
    if _es_client is None:
        _es_client = AsyncElasticsearch(hosts=[ELASTIC_HOST])
    return _es_client


async def search_faqs(
    es_client: AsyncElasticsearch,
    customer_id: str,
    query: str,
) -> List[Dict[str, Any]]:
    """Tìm kiếm câu hỏi tương tự trong index FAQ."""
    if not es_client:
        return []

    sanitized_customer_id = sanitize_for_es(customer_id)

    try:
        response = await es_client.search(
            index=FAQ_INDEX,
            query={
                "bool": {
                    "must": [
                        {"term": {"customer_id": sanitized_customer_id}},
                        {"match": {"question": query}},
                    ]
                }
            },
            routing=sanitized_customer_id,
            size=1,
        )
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        print(f"Lỗi khi tìm kiếm FAQ: {e}")
        return []


@mcp.tool()
async def faq_search(customer_id: str, query: str) -> Dict[str, Any]:
    """Tìm kiếm câu hỏi tương tự trong kho FAQ của một customer."""

    es = await _get_es_client()
    try:
        results = await search_faqs(es_client=es, customer_id=customer_id, query=query)
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
