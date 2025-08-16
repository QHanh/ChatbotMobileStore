from elasticsearch import Elasticsearch
from config.settings import ELASTIC_HOST

# Shared state variables
chat_memory = {}
customer_configs = {}

# Initialize Elasticsearch client
es_client = None
try:
    es_client = Elasticsearch(hosts=[ELASTIC_HOST])
    if not es_client.ping():
        raise ConnectionError("Could not connect to Elasticsearch.")
    print("Successfully connected to Elasticsearch.")
except ConnectionError as e:
    print(f"Elasticsearch connection error: {e}")
    es_client = None
