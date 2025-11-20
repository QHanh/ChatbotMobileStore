"""MCP server cho domain sản phẩm (products).

Skeleton này mô tả cách expose logic ``search_products`` hiện tại qua MCP.
Sau này server này sẽ được chạy như một process riêng, backend sẽ gọi qua langchain-mcp-adapters.
"""

from typing import Any, Dict, Optional

from elasticsearch import AsyncElasticsearch
from config.settings import ELASTIC_HOST
from mcp.server.fastmcp import FastMCP

# Import shared logic
from service.retrieve.search_service import search_products
from chat_mcp.core.constants import TOOL_PRODUCTS_SEARCH


mcp = FastMCP(name="products-mcp")

_es_client: Optional[AsyncElasticsearch] = None


async def _get_es_client() -> AsyncElasticsearch:
    """Khởi tạo/lấy lại client Elasticsearch dùng chung cho MCP server products.

    Đơn giản hoá: giữ một AsyncElasticsearch toàn cục trong process MCP.
    """

    global _es_client
    if _es_client is None:
        _es_client = AsyncElasticsearch(hosts=[ELASTIC_HOST])
    return _es_client


@mcp.tool(name=TOOL_PRODUCTS_SEARCH)
async def products_search(
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
) -> Dict[str, Any]:
    """Tìm kiếm sản phẩm cho một customer.

    Tham số:
    - customer_id: mã khách hàng (tenant).
    - thread_id: mã phiên chat, dùng để phân biệt khách lẻ/buôn như logic cũ.
    - query: câu hỏi gốc của người dùng, map sang ``original_query``.
    - offset: phân trang (bỏ qua N kết quả đầu).

    Triển khai:
    - Gọi lại hàm ``search_products`` trong ``service.retrieve.search_service``.
    - Tạm thời map query → original_query, chưa bẻ nhỏ thành model/màu/dung lượng.
    """

    es = await _get_es_client()
    try:
        # Gọi trực tiếp service logic đã có
        results = await search_products(
            es_client=es,
            customer_id=customer_id,
            thread_id=thread_id,
            model=None,
            mau_sac=None,
            dung_luong=None,
            tinh_trang_may=None,
            loai_thiet_bi=None,
            min_gia=None,
            max_gia=None,
            offset=offset,
            original_query=query,
            llm=None,
            chat_history=None,
        )
        return {"results": results}
    except Exception as e:
        # MCP tool nên luôn trả về JSON, nên bọc lỗi thành field error.
        return {"error": str(e)}


if __name__ == "__main__":
    # Khi chạy trực tiếp file này, khởi động MCP server products-mcp.
    mcp.run()
