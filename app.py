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
    info_store_routes
)
from database.database import init_db
import dependencies
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
    # Initialize all clients on startup
    await dependencies.init_es_client()
    await dependencies.init_weaviate_client()
    
    yield
    
    # Close all clients on shutdown
    print("Application shutdown...")
    await dependencies.close_es_client()
    await dependencies.close_weaviate_client()
    print("All clients closed. Shutdown complete.")

app = FastAPI(**APP_CONFIG, lifespan=lifespan)

app.mount("/images", StaticFiles(directory="JS_Chatbot/images"), name="images")

app.add_middleware(CORSMiddleware, **CORS_CONFIG)

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

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=True)