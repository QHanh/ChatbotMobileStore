import os
import weaviate
from typing import List, Dict, Any
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, Docx2txtLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_weaviate.vectorstores import WeaviateVectorStore
from langchain_core.documents import Document
import tempfile

# Cấu hình kết nối Weaviate
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

def get_weaviate_client():
    """
    Khởi tạo và trả về một client Weaviate.
    """
    client_params = {
        "url": WEAVIATE_URL,
    }
    if WEAVIATE_API_KEY:
        client_params["auth_client_secret"] = weaviate.AuthApiKey(api_key=WEAVIATE_API_KEY)
    
    try:
        client = weaviate.Client(**client_params)
        if not client.is_ready():
            raise ConnectionError("Không thể kết nối đến Weaviate.")
        print("Kết nối đến Weaviate thành công!")
        return client
    except Exception as e:
        print(f"Lỗi khi kết nối đến Weaviate: {e}")
        return None

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

def load_chunks_to_weaviate(client: weaviate.Client, chunks: List[Dict[str, Any]], class_name: str):
    """
    Tải các chunk văn bản vào Weaviate.
    """
    print(f"Chuẩn bị tải {len(chunks)} chunk vào Weaviate class: '{class_name}'...")

    try:
        WeaviateVectorStore.from_documents(
            documents=chunks,
            client=client,
            index_name=class_name,
            text_key="text" # Đảm bảo text_key khớp với schema của bạn
        )
        print("Tải dữ liệu lên Weaviate thành công!")
    except Exception as e:
        print(f"Lỗi khi tải dữ liệu lên Weaviate: {e}")

def process_and_load_text(client: weaviate.Client, text: str, class_name: str):
    """
    Xử lý văn bản thô, chia nhỏ và tải vào Weaviate.
    """
    documents = [Document(page_content=text)]
    chunks = split_documents(documents)
    load_chunks_to_weaviate(client, chunks, class_name)

def process_and_load_file(client: weaviate.Client, file_content: bytes, file_name: str, class_name: str):
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
