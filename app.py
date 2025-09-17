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
    order_routes
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
from weaviate.auth import AuthApiKey
from weaviate.client import WeaviateClient
from weaviate.connect import ConnectionParams


load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup...")
    # Startup logic
    await dependencies.init_es_client()
    
    # Initialize Weaviate client on startup
    WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
    connection_params = ConnectionParams.from_url(url=WEAVIATE_URL, grpc_port=50051)
    auth_credentials = AuthApiKey(WEAVIATE_API_KEY) if WEAVIATE_API_KEY else None
    
    # Modify the variable within the dependencies module
    client_config = {"connection_params": connection_params}
    if auth_credentials:
        client_config["auth_client_secret"] = auth_credentials
        
    dependencies._weaviate_client = WeaviateClient(**client_config)
    try:
        dependencies._weaviate_client.connect()
        print("Successfully connected to Weaviate!")
    except Exception as e:
        print(f"Error connecting to Weaviate on startup: {e}")
        dependencies._weaviate_client = None

    yield

    # Shutdown logic
    if dependencies.es_client:
        await dependencies.es_client.close()
        print("Elasticsearch client closed.")
    if dependencies._weaviate_client and dependencies._weaviate_client.is_connected():
        dependencies._weaviate_client.close()
        print("Weaviate client closed.")

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


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=True)