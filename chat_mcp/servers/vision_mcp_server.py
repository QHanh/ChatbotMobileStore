"""MCP server cho domain vision (nhận diện sản phẩm từ ảnh).

Skeleton này wrap logic _identify_product_from_image hiện tại qua MCP.
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP


mcp = FastMCP(name="vision-mcp")


@mcp.tool()
async def vision_identify_product(
    customer_id: str,
    image_urls: Optional[List[str]] = None,
    image_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """Nhận diện sản phẩm/tài liệu từ ảnh cho một customer.

    Giai đoạn skeleton:
    - Sau này wrap lại hàm _identify_product_from_image trong api.chat_routes.
    - Output dự kiến: product_spec, candidates, confidence, citations.
    """
    # TODO: implement gọi _identify_product_from_image(...) với LLM vision thật.
    return {"product_spec": None, "candidates": [], "confidence": 0.0, "citations": []}


if __name__ == "__main__":
    mcp.run()
