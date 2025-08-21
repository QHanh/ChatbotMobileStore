import os
import weaviate
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, Docx2txtLoader, TextLoader

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_weaviate.vectorstores import WeaviateVectorStore
from langchain_core.documents import Document
from weaviate.classes.config import Configure, Property, DataType
import tempfile
from weaviate.auth import AuthApiKey
from dotenv import load_dotenv
from weaviate.client import WeaviateClient
from weaviate.connect import ConnectionParams
import re
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
DOCUMENT_CLASS_NAME = "Document"

def ensure_document_collection_exists(client: weaviate.WeaviateClient):
    """
    Đảm bảo class 'Document' tồn tại và được cấu hình cho multi-tenancy.
    """
    if not client.collections.exists(DOCUMENT_CLASS_NAME):
        print(f"Collection '{DOCUMENT_CLASS_NAME}' chưa tồn tại. Đang tạo...")
        try:
            client.collections.create(
                name=DOCUMENT_CLASS_NAME,
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="source", data_type=DataType.TEXT),
                ],
                multi_tenancy_config=Configure.multi_tenancy(enabled=True)
            )
            print(f"✅ Đã tạo thành công collection '{DOCUMENT_CLASS_NAME}' với multi-tenancy!")
        except Exception as e:
            print(f"❌ Lỗi khi tạo collection '{DOCUMENT_CLASS_NAME}': {e}")
            raise
    else:
        print(f"Collection '{DOCUMENT_CLASS_NAME}' đã tồn tại.")

def ensure_tenant_exists(client: weaviate.WeaviateClient, tenant_id: str):
    """
    Đảm bảo một tenant tồn tại trong collection 'Document'.
    Lưu ý: tenant_id chính là customer_id đã được làm sạch.
    """
    collection = client.collections.get(DOCUMENT_CLASS_NAME)
    if not collection.tenants.exists(tenant_id):
        print(f"Tenant '{tenant_id}' chưa tồn tại. Đang tạo...")
        collection.tenants.create(tenant_id)
        print(f"✅ Đã tạo tenant '{tenant_id}'.")

def get_weaviate_client():
    """
    Establishes a connection to the Weaviate instance with proper authentication.
    """
    auth_credentials = AuthApiKey(WEAVIATE_API_KEY) if WEAVIATE_API_KEY else None

    client = WeaviateClient(
        connection_params=ConnectionParams.from_url(url=WEAVIATE_URL, grpc_port=50051),
        auth_client_secret=auth_credentials
    )
    
    client.connect()

    if not client.is_ready():
        client.close() 
        raise ConnectionError("Không thể kết nối đến Weaviate.")
    
    print("Kết nối đến Weaviate thành công!")
    return client

def load_documents_from_directory(path: str) -> List[Dict[str, Any]]:
    """
    Tải tài liệu từ một thư mục, hỗ trợ các định dạng PDF, DOCX, và TXT.
    """
    print(f"Đang tải tài liệu từ thư mục: {path}")
    
    loader = DirectoryLoader(
        path,
        glob="**/*",
        use_multithreading=True,
        show_progress=True,
        loader_map={
            ".pdf": PyPDFLoader,
            ".docx": Docx2txtLoader,
            ".txt": TextLoader,
            ".md": TextLoader,
            ".json": TextLoader,
        },
    )
    documents = loader.load()
    print(f"Đã tải thành công {len(documents)} tài liệu.")
    return documents

def split_documents(documents: List[Dict[str, Any]], chunk_size: int = 500, chunk_overlap: int = 50) -> List[Dict[str, Any]]:
    """
    Chia nhỏ tài liệu thành các chunk văn bản bằng RecursiveCharacterTextSplitter.
    """
    print(f"Đang chia nhỏ {len(documents)} tài liệu thành các chunk...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        add_start_index=True,
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Đã tạo thành công {len(chunks)} chunk văn bản.")
    return chunks

def load_chunks_to_weaviate(client: weaviate.WeaviateClient, chunks: List[Document], tenant_id: str):
    """
    Tải các chunk văn bản vào một tenant cụ thể của Weaviate.
    """
    print(f"Chuẩn bị tải {len(chunks)} chunk vào tenant: '{tenant_id}'...")

    def _sanitize_property_name(name: str) -> str:
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if name and name[0].isdigit():
            name = f"_{name}"
        return name

    for chunk in chunks:
        if chunk.metadata:
            chunk.metadata = {
                _sanitize_property_name(key): value
                for key, value in chunk.metadata.items()
            }

    try:
        # Khởi tạo và sử dụng Google Embeddings để tạo vector
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        
        # Lấy collection và chỉ định tenant để làm việc
        collection = client.collections.get(DOCUMENT_CLASS_NAME)
        tenant_collection = collection.with_tenant(tenant_id)

        WeaviateVectorStore.from_documents(
            documents=chunks,
            embedding=embeddings,
            client=client,
            index_name=DOCUMENT_CLASS_NAME,
            text_key="text",
            tenant=tenant_id
        )
        print("Tải dữ liệu lên Weaviate thành công!")
    except Exception as e:
        print(f"Lỗi khi tải dữ liệu lên Weaviate: {e}")
        raise

def process_and_load_text(client: weaviate.WeaviateClient, text: str, source_name: str, tenant_id: str):
    """
    Xử lý văn bản thô, chia nhỏ và tải vào Weaviate cho một tenant.
    """
    metadata = {"source": source_name}
    documents = [Document(page_content=text, metadata=metadata)]
    chunks = split_documents(documents)
    load_chunks_to_weaviate(client, chunks, tenant_id)

def process_and_load_file(client: weaviate.WeaviateClient, file_content: bytes, source_name: str, original_filename: str, tenant_id: str):
    """
    Xử lý tệp, chia nhỏ và tải vào Weaviate cho một tenant.
    """
    file_ext = os.path.splitext(original_filename)[1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        tmp_file.write(file_content)
        tmp_file_path = tmp_file.name

    loader_cls = None
    if file_ext == ".pdf":
        loader_cls = PyPDFLoader
    elif file_ext == ".docx":
        loader_cls = Docx2txtLoader
    elif file_ext in [".txt", ".md"]:
        loader_cls = TextLoader
    elif file_ext == ".json":
        loader_cls = TextLoader

    if loader_cls:
        loader = loader_cls(tmp_file_path)
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = source_name
            
        chunks = split_documents(documents)
        load_chunks_to_weaviate(client, chunks, tenant_id)
    else:
        # Xóa file tạm nếu không có loader phù hợp
        os.remove(tmp_file_path)
        raise ValueError(f"Không hỗ trợ định dạng file: {file_ext}")
    
    os.remove(tmp_file_path)
