"""Legacy file.

Routers for MCP configuration have been split into dedicated modules:
- mcp_server_routes.py: /config/mcp/servers...
- agent_binding_routes.py: /config/agents/... and effective config.

Use mcp.api (from mcp import router) as the main entry point.
"""

from .mcp_server_routes import router as mcp_server_router  # noqa: F401
from .agent_binding_routes import router as agent_binding_router  # noqa: F401

