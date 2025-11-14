from fastapi import APIRouter

from .mcp_server_routes import router as mcp_server_router
from .agent_binding_routes import router as agent_binding_router

router = APIRouter()
router.include_router(mcp_server_router)
router.include_router(agent_binding_router)

__all__ = ["router"]
