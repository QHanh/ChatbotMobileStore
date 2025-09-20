from elasticsearch import AsyncElasticsearch
from config.settings import ELASTIC_HOST
import weaviate
from weaviate.client import WeaviateClient
from weaviate.connect import ConnectionParams
from service.integrations.sheet_service import get_gspread_client
from elasticsearch import AsyncElasticsearch
from typing import Optional
import os
from weaviate.auth import AuthApiKey
from sqlalchemy.orm import Session
from database.database import SessionLocal
from fastapi import HTTPException

es_client: AsyncElasticsearch = None
_weaviate_client: Optional[WeaviateClient] = None

async def init_es_client():
    """
    Initializes and returns a single instance of the Elasticsearch client.
    """
    global es_client
    if es_client is None:
        try:
            es_client = AsyncElasticsearch(hosts=[ELASTIC_HOST])
            if not await es_client.ping():
                raise ConnectionError("Could not connect to Elasticsearch")
            print("Successfully connected to Elasticsearch!")
        except ConnectionError as e:
            print(f"Error connecting to Elasticsearch: {e}")
            es_client = None

async def close_es_client():
    """
    Closes the Elasticsearch client connection.
    """
    global es_client
    if es_client:
        await es_client.close()
        es_client = None
        print("Elasticsearch client closed.")

def get_es_client() -> AsyncElasticsearch:
    """
    Dependency provider for the Elasticsearch client.
    Returns the initialized client instance.
    """
    return es_client

async def init_weaviate_client():
    """
    Initializes the singleton Weaviate client instance.
    """
    global _weaviate_client
    if _weaviate_client is None:
        try:
            WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
            WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
            connection_params = ConnectionParams.from_url(url=WEAVIATE_URL, grpc_port=50051)
            auth_credentials = AuthApiKey(WEAVIATE_API_KEY) if WEAVIATE_API_KEY else None
            
            client_config = {"connection_params": connection_params}
            if auth_credentials:
                client_config["auth_client_secret"] = auth_credentials
                
            _weaviate_client = WeaviateClient(**client_config)
            _weaviate_client.connect()
            print("Successfully connected to Weaviate!")
        except Exception as e:
            print(f"Error connecting to Weaviate on startup: {e}")
            _weaviate_client = None

async def close_weaviate_client():
    """
    Closes the Weaviate client connection.
    """
    global _weaviate_client
    if _weaviate_client and _weaviate_client.is_connected():
        _weaviate_client.close()
        _weaviate_client = None
        print("Weaviate client closed.")

def get_weaviate_client() -> WeaviateClient:
    """
    Dependency provider for the Weaviate client.
    Returns the initialized singleton client instance.
    """
    if _weaviate_client is None:
        raise RuntimeError("Weaviate client is not initialized. Please check the application's lifespan management.")
    return _weaviate_client

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_gspread_client_dep():
    try:
        return get_gspread_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not initialize Google Sheets client: {e}")
