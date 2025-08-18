from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from config.settings import APP_CONFIG, CORS_CONFIG
from api import product_routes, service_routes, accessory_routes, config_routes, chat_routes, document_routes
import logging
logging.getLogger("watchfiles").setLevel(logging.ERROR)

app = FastAPI(**APP_CONFIG)

app.add_middleware(CORSMiddleware, **CORS_CONFIG)

app.include_router(product_routes.router, tags=["Products"])
app.include_router(service_routes.router, tags=["Services"])
app.include_router(accessory_routes.router, tags=["Accessories"])
app.include_router(document_routes.router, tags=["Documents"])
app.include_router(config_routes.router, tags=["Configuration"])
app.include_router(chat_routes.router, tags=["Chat"])

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=True)