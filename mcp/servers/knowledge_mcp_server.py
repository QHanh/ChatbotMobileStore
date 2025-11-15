"""MCP server cho domain tri thức/GraphRAG (knowledge).

Wrap logic ``graphrag_search_logic`` hiện tại qua MCP.
"""

from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from service.graphrag.graphrag_service import (
    workspace_path_for_customer,
    run_query,
)


mcp = FastMCP(name="knowledge-mcp")


async def graphrag_search_logic(
    customer_id: str,
    method: str,
    query: str,
    community_level: Optional[int] = None,
    response_type: Optional[str] = None,
) -> str:
    """Truy vấn GraphRAG Query Engine trên workspace của khách hàng.

    method: 'local' | 'global' | 'drift' | 'basic'
    """
    print(f"--- Agent đã gọi GraphRAG Query: customer={customer_id}, method={method} ---")
    root = workspace_path_for_customer(customer_id)
    output = run_query(
        root=root,
        method=method,
        query=query,
        community_level=community_level,
        response_type=response_type,
    )
    return output or ""


@mcp.tool()
async def knowledge_graphrag(
    customer_id: str,
    mode: str,
    query: str,
    community_level: Optional[int] = None,
    response_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Truy vấn GraphRAG cho một customer.

    - mode: 'local' | 'global' | 'drift' | 'basic'.
    - community_level, response_type: tham số phụ như logic cũ.
    """

    try:
        answer = await graphrag_search_logic(
            customer_id=customer_id,        
            method=mode,
            query=query,
            community_level=community_level,
            response_type=response_type,
        )
        return {"answer": answer}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
