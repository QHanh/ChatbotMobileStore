from elasticsearch import AsyncElasticsearch
from config.settings import ELASTIC_HOST
from langchain.memory import ConversationBufferWindowMemory
import weaviate

es_client: AsyncElasticsearch = None
chat_memory = {}
weaviate_client: weaviate.Client = None

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

def get_weaviate_client() -> weaviate.Client:
    """
    Initializes and returns a single instance of the Weaviate client.
    """
    global weaviate_client
    if weaviate_client is None:
        try:
            weaviate_client = weaviate.Client("http://weaviate:8080")
            if not weaviate_client.is_ready():
                 raise ConnectionError("Could not connect to Weaviate")
            print("Successfully connected to Weaviate!")
        except ConnectionError as e:
            print(f"Error connecting to Weaviate: {e}")
            weaviate_client = None
    return weaviate_client
