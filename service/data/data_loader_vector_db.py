import os
import weaviate
from typing import List, Dict, Any
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

load_dotenv()

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

def ensure_collection_exists(client: weaviate.WeaviateClient, class_name: str):
    """
    Kiểm tra xem một collection đã tồn tại chưa. Nếu chưa, tạo nó với cấu hình đúng.
    """
    if not client.collections.exists(class_name):
        print(f"Collection '{class_name}' chưa tồn tại. Đang tạo...")
        try:
            client.collections.create(
                name=class_name,
                vectorizer_config=Configure.Vectorizer.custom(
                    vectorizer="text2vec-model2vec" 
                ),
                properties=[
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="source", data_type=DataType.TEXT)
                ]
            )
            print(f"✅ Đã tạo thành công collection '{class_name}'!")
        except Exception as e:
            print(f"❌ Lỗi khi tạo collection '{class_name}': {e}")
            raise
    else:
        print(f"Collection '{class_name}' đã tồn tại.")
        # Đảm bảo thuộc tính 'source' tồn tại trong schema để dùng cho liệt kê
        try:
            collection = client.collections.get(class_name)
            collection.config.add_property(Property(name="source", data_type=DataType.TEXT))
            print("Đã đảm bảo thuộc tính 'source' tồn tại trong schema.")
        except Exception as e:
            # Bỏ qua nếu thuộc tính đã tồn tại hoặc không thể thêm vì lý do khác
            print(f"Bỏ qua thêm thuộc tính 'source': {e}")

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

def load_chunks_to_weaviate(client: weaviate.WeaviateClient, chunks: List[Dict[str, Any]], class_name: str):
    """
    Tải các chunk văn bản vào Weaviate.
    """
    print(f"Chuẩn bị tải {len(chunks)} chunk vào Weaviate class: '{class_name}'...")
    try:
        WeaviateVectorStore.from_documents(
            documents=chunks,
            embedding=None,
            client=client,
            index_name=class_name,
            text_key="text"
        )
        print("Tải dữ liệu lên Weaviate thành công!")
        client.close()
    except Exception as e:
        print(f"Lỗi khi tải dữ liệu lên Weaviate: {e}")

def process_and_load_text(client: weaviate.WeaviateClient, text: str, class_name: str):
    """
    Xử lý văn bản thô, chia nhỏ và tải vào Weaviate.
    """
    documents = [Document(page_content=text)]
    chunks = split_documents(documents)
    load_chunks_to_weaviate(client, chunks, class_name)

def process_and_load_file(client: weaviate.WeaviateClient, file_content: bytes, file_name: str, class_name: str):
    """
    Xử lý tệp, chia nhỏ và tải vào Weaviate.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp_file:
        tmp_file.write(file_content)
        tmp_file_path = tmp_file.name

    loader_cls = None
    file_ext = os.path.splitext(file_name)[1].lower()
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
        chunks = split_documents(documents)
        load_chunks_to_weaviate(client, chunks, class_name)
    
    os.remove(tmp_file_path)
