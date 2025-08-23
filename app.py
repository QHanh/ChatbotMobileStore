from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from config.settings import APP_CONFIG, CORS_CONFIG
from api import product_routes, service_routes, accessory_routes, config_routes, chat_routes, document_routes, instruction_routes
from database.database import init_db
from dependencies import init_es_client, close_es_client, es_client
from service.data.data_loader_elastic_search import ensure_shared_indices_exist
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup...")
    await init_es_client()
    if es_client:
        await ensure_shared_indices_exist(es_client)
    # init_db()
    yield
    print("Application shutdown.")
    await close_es_client()

app = FastAPI(**APP_CONFIG, lifespan=lifespan)

app.add_middleware(CORSMiddleware, **CORS_CONFIG)

app.include_router(product_routes.router, tags=["Products"])
app.include_router(service_routes.router, tags=["Services"])
app.include_router(accessory_routes.router, tags=["Accessories"])
app.include_router(document_routes.router, tags=["Documents"])
app.include_router(config_routes.router, tags=["Configuration"])
app.include_router(instruction_routes.router, tags=["Instructions"])
app.include_router(chat_routes.router, tags=["Chat"])

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=True)