from elasticsearch import AsyncElasticsearch
from config.settings import ELASTIC_HOST

es_client = AsyncElasticsearch(hosts=ELASTIC_HOST)
chat_memory = {}
