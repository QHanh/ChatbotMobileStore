"""API package entrypoint for MCP.

Hiện tại toàn bộ HTTP endpoint của MCP (config servers, agent bindings,
và chat-mcp) được gộp trong ``mcp.api.routes``.

Module này chỉ re-export ``router`` để `from mcp import router` hoặc
`from mcp.api import router` đều dùng chung một router.
"""

from .routes import router

__all__ = ["router"]
