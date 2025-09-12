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

def get_weaviate_client() -> WeaviateClient:
    """
    Returns the existing singleton Weaviate client instance.
    The client is expected to be initialized and closed by the application's lifespan manager.
    """
    if _weaviate_client is None or not _weaviate_client.is_connected():
        raise RuntimeError("Weaviate client is not initialized or connected. Please check the application's lifespan management.")
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
