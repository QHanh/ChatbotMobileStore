from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from config.settings import APP_CONFIG, CORS_CONFIG
from api import (
    product_routes, 
    service_routes, 
    accessory_routes, 
    chat_routes, 
    config_routes,
    document_routes,
    instruction_routes,
    faq_routes,
    control_routes,
    setting_routes,
    order_routes,
    info_store_routes,
    graphrag_routes,
    training_routes,
)
from chat_mcp import router as mcp_router
from chat_mcp.services import MCPClientManager
from chat_mcp.agents.orchestrator import prewarm_tenant_graph
from database.database import init_db, SessionLocal, MCPAgentBinding
import dependencies
from app_logging.error_handler import ErrorHandlerMiddleware
import os
os.environ["LANGCHAIN_DEBUG"] = "true"
import tracemalloc
tracemalloc.start()
import logging
logging.getLogger("watchfiles").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
from pydantic.warnings import PydanticDeprecatedSince20
import warnings
warnings.filterwarnings(
    "ignore",
    category=PydanticDeprecatedSince20,
    module=r"langchain_core\.tools\.base",
)
import os
from dotenv import load_dotenv
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's startup and shutdown events.
    Initializes and closes necessary client connections.
    """
    print("Application startup...")
    await dependencies.init_es_client()

    db = SessionLocal()
    try:
        client_manager = MCPClientManager()
        tenant_rows = db.query(MCPAgentBinding.tenant_id).distinct().all()
        tenant_ids = [row[0] for row in tenant_rows]
        print(f"[MCP] Startup: found tenants {tenant_ids}")
        mcp_errors = []
        for tenant_id in tenant_ids:
            try:
                effective_config = client_manager.get_effective_config_for_tenant(db, tenant_id)
                await prewarm_tenant_graph(db, tenant_id, effective_config)
                print(f"[MCP] Prewarm success for tenant {tenant_id}")
            except Exception as e:
                error_msg = f"[MCP] Error during prewarm for tenant {tenant_id}: {e}"
                print(error_msg)
                mcp_errors.append(error_msg)
        if not mcp_errors:
            print("[MCP] Startup completed successfully for all tenants")
        else:
            print(f"[MCP] Startup completed with {len(mcp_errors)} error(s)")
    finally:
        db.close()

    yield
    
    # Close all clients on shutdown
    print("Application shutdown...")
    await dependencies.close_es_client()
    print("All clients closed. Shutdown complete.")

app = FastAPI(**APP_CONFIG, lifespan=lifespan)

app.mount("/images", StaticFiles(directory="JS_Chatbot/images"), name="images")

app.add_middleware(CORSMiddleware, **CORS_CONFIG)

app.add_middleware(ErrorHandlerMiddleware)

app.include_router(product_routes.router, tags=["Products"])
app.include_router(service_routes.router, tags=["Services"])
app.include_router(accessory_routes.router, tags=["Accessories"])
app.include_router(document_routes.router, tags=["Documents"])
app.include_router(config_routes.router, tags=["Configuration"])
app.include_router(instruction_routes.router, tags=["Instructions"])
app.include_router(faq_routes.router, tags=["FAQ"])
app.include_router(control_routes.router, tags=["Control"])
app.include_router(chat_routes.router, tags=["Chat"])
app.include_router(setting_routes.router, tags=["Settings"])
app.include_router(order_routes.router, tags=["Orders"])
app.include_router(info_store_routes.router, tags=["Store Info"])
app.include_router(graphrag_routes.router, tags=["GraphRAG"])
app.include_router(training_routes.router, tags=["Training"])
app.include_router(mcp_router, tags=["MCP"])

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8010, reload=False)