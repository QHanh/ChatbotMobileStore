import os
import weaviate
from typing import List, Dict, Any
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, Docx2txtLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_weaviate.vectorstores import WeaviateVectorStore

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
        },
    )
    documents = loader.load()
    print(f"Đã tải thành công {len(documents)} tài liệu.")
    return documents

def split_documents(documents: List[Dict[str, Any]], chunk_size: int = 1000, chunk_overlap: int = 150) -> List[Dict[str, Any]]:
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

def main(data_path: str, weaviate_class: str):
    """
    Hàm chính để thực hiện quy trình tải và nhúng tài liệu.
    """
    # 1. Kết nối đến Weaviate
    client = get_weaviate_client()
    if not client:
        return

    # 2. Tải và xử lý tài liệu
    documents = load_documents_from_directory(data_path)
    if not documents:
        print("Không tìm thấy tài liệu nào để xử lý.")
        return
        
    # 3. Chia nhỏ tài liệu
    chunks = split_documents(documents)

    # 4. Tải chunks vào Weaviate
    load_chunks_to_weaviate(client, chunks, weaviate_class)

if __name__ == "__main__":
    # Thay đổi đường dẫn đến thư mục chứa dữ liệu của bạn
    DATA_DIRECTORY = "path/to/your/data" 
    # Thay đổi tên class (collection) trong Weaviate mà bạn muốn lưu dữ liệu
    WEAVIATE_CLASS_NAME = "MyDocumentCollection" 

    if not os.path.exists(DATA_DIRECTORY):
        print(f"Lỗi: Thư mục '{DATA_DIRECTORY}' không tồn tại. Vui lòng cung cấp đường dẫn hợp lệ.")
    else:
        main(DATA_DIRECTORY, WEAVIATE_CLASS_NAME)
