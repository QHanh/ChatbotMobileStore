import pandas as pd
from elasticsearch import Elasticsearch, AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk
import numpy as np
import warnings
import io
import os
from service.utils.helpers import sanitize_for_es
from typing import List, Dict, Any
from datetime import datetime, timezone
import hashlib
from google import genai
from google.genai import types

warnings.filterwarnings("ignore", category=UserWarning)

PRODUCTS_INDEX = "products"
SERVICES_INDEX = "services"
ACCESSORIES_INDEX = "accessories"
FAQ_INDEX = "faqs"

def get_shared_index_mapping(data_type: str):
    """
    Trả về mapping cho một loại dữ liệu cụ thể, đã bao gồm trường 'customer_id'.
    """
    common_properties = {
        "customer_id": {"type": "keyword"}
    }
    if data_type == "product":
        specific_properties = {
            "ma_san_pham": {"type": "keyword"},
            "model": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "mau_sac": {"type": "keyword"},
            "dung_luong": {"type": "keyword"},
            "tinh_trang_may": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "loai_thiet_bi": {"type": "keyword"},
            "gia": {"type": "double"},
            "gia_buon": {"type": "double"},
            "ton_kho": {"type": "integer"},
            # Vector embedding cho tên thiết bị (model) để dùng hybrid search trong Elasticsearch
            "model_embedding": {
                "type": "dense_vector",
                "dims": 768,
                "index": True,
                "similarity": "cosine",
            },
        }
    elif data_type == "service":
        specific_properties = {
            "ma_dich_vu": {"type": "keyword"},
            "ten_dich_vu": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "ten_san_pham": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "gia": {"type": "double"},
            "gia_buon": {"type": "double"},
            # Vector embedding cho tên dịch vụ
            "ten_dich_vu_embedding": {
                "type": "dense_vector",
                "dims": 768,
                "index": True,
                "similarity": "cosine",
            },
        }
    elif data_type == "accessory":
        specific_properties = {
            "accessory_code": {"type": "keyword"},
            "accessory_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "category": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "properties": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "lifecare_price": {"type": "double"},
            "sale_price": {"type": "double"},
            "trademark": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "guarantee": {"type": "text"},
            "inventory": {"type": "integer"},
            "specifications": {"type": "text"},
            "avatar_images": {"type": "keyword"},
            "link_accessory": {"type": "keyword"},
            # Vector embedding cho tên phụ kiện
            "accessory_name_embedding": {
                "type": "dense_vector",
                "dims": 768,
                "index": True,
                "similarity": "cosine",
            },
        }
    elif data_type == "faq":
        specific_properties = {
            "faq_id": {"type": "keyword"},
            "question": {"type": "text", "analyzer": "standard"},
            "answer": {"type": "text", "analyzer": "standard"},
            "classification": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "created_at": {"type": "date"}
        }
    else:
        return {}
        
    common_properties.update(specific_properties)
    return {"properties": common_properties}

async def ensure_shared_indices_exist(es_client: Elasticsearch):
    """
    Kiểm tra và tạo các index chia sẻ nếu chúng chưa tồn tại.
    """
    indices_to_create = {
        PRODUCTS_INDEX: "product",
        SERVICES_INDEX: "service",
        ACCESSORIES_INDEX: "accessory",
        FAQ_INDEX: "faq"
    }
    for index_name, data_type in indices_to_create.items():
        if not await es_client.indices.exists(index=index_name):
            print(f"🛠 Đang tạo index chia sẻ '{index_name}'...")
            mapping = get_shared_index_mapping(data_type)
            await es_client.indices.create(index=index_name, mappings=mapping)
            print(f"✅ Tạo thành công index '{index_name}'.")

async def clear_customer_data(es_client: Elasticsearch, index_name: str, customer_id: str):
    """
    Xóa tất cả dữ liệu của một customer_id cụ thể khỏi một index.
    """
    print(f"🗑️ Đang xóa dữ liệu cũ của khách hàng '{customer_id}' trong index '{index_name}'...")
    sanitized_customer_id = sanitize_for_es(customer_id)
    try:
        await es_client.delete_by_query(
            index=index_name,
            query={"term": {"customer_id": sanitized_customer_id}},
            refresh=True,
            wait_for_completion=True
        )
        print(f"✅ Xóa dữ liệu cũ thành công.")
    except Exception as e:
        print(f"⚠️ Không thể xóa dữ liệu cũ (có thể do chưa có): {e}")

async def process_and_index_data(
    es_client: Elasticsearch, 
    customer_id: str,
    index_name: str, 
    file_content: bytes, 
    columns_config: dict,
    embed_name_field: str | None = None,
):
    """
    Hàm tổng quát để đọc, xử lý và nạp dữ liệu vào một index chia sẻ.
    """
    await clear_customer_data(es_client, index_name, customer_id)
    sanitized_customer_id = sanitize_for_es(customer_id)
    try:
        df = pd.read_excel(io.BytesIO(file_content))
        
        config_cols = columns_config.get('names', [])
        rename_map = columns_config.get('rename_map', {})

        missing_cols = [col for col in config_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Các cột sau không tìm thấy trong file Excel: {', '.join(missing_cols)}")

        df = df[config_cols]

        for col in columns_config.get('required', []):
            if pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].str.strip()
            df[col] = df[col].replace(r'^\s*$', np.nan, regex=True)

        df = df.dropna(subset=columns_config['required'])
        
        for col, dtype in columns_config.get('numerics', {}).items():
            if dtype == float:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).astype(float)
            elif dtype == int:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        
        if rename_map:
            df.rename(columns=rename_map, inplace=True)
            
        df['customer_id'] = sanitized_customer_id
        df = df.where(pd.notnull(df), None).replace({np.nan: None})
    except Exception as e:
        raise ValueError(f"Lỗi đọc hoặc xử lý file Excel: {e}")

    actions = []
    original_id_field = columns_config.get('id_field')
    renamed_id_field = rename_map.get(original_id_field, original_id_field)

    for _, row in df.iterrows():
        doc = row.to_dict()
        product_id = doc.get(renamed_id_field)
        if product_id is None:
            continue

        # Nếu được cấu hình, embed tên và lưu vào <field>_embedding
        if embed_name_field:
            try:
                name_value = doc.get(embed_name_field)
                if name_value is not None:
                    embedding = await _embed_name_with_google(str(name_value))
                    doc[f"{embed_name_field}_embedding"] = embedding
            except Exception as e:
                print(f"⚠️ Lỗi embed cho document {product_id}: {e}")

        sanitized_product_id = sanitize_for_es(str(product_id))

        action = {
            "_index": index_name,
            "_id": f"{sanitized_customer_id}_{sanitized_product_id}",
            "_source": doc,
            "routing": sanitized_customer_id,
        }
        actions.append(action)

    if not actions:
        return 0, 0

    print(f"🚀 Đang nạp {len(actions)} bản ghi vào index '{index_name}' cho khách hàng '{customer_id}'...")
    try:
        success, failed = await async_bulk(es_client, actions, raise_on_error=False, refresh=True)
        print(f"✅ Thành công: {success} bản ghi.")
        if failed:
            print(f"❌ Thất bại: {len(failed)} bản ghi.")
            print("--- Chi tiết 5 lỗi đầu tiên ---")
            for i, fail_info in enumerate(failed[:5]):
                error_details = fail_info.get('index', {}).get('error', 'Không có chi tiết lỗi.')
                doc_id = fail_info.get('index', {}).get('_id', 'N/A')
                print(f"  Lỗi {i+1} (ID: {doc_id}): {error_details}")
            print("---------------------------------")
        return success, len(failed)
    except Exception as e:
        raise IOError(f"Lỗi trong quá trình bulk indexing: {e}")


_genai_client: genai.Client | None = None


def _get_genai_client() -> genai.Client:
    """Khởi tạo client Google GenAI dùng chung trong module."""
    global _genai_client
    if _genai_client is not None:
        return _genai_client

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    _genai_client = genai.Client(api_key=api_key) if api_key else genai.Client()
    return _genai_client


async def _embed_name_with_google(text: str) -> List[float]:
    """Tạo embedding cho tên (sản phẩm/dịch vụ/phụ kiện) bằng Google Gemini.

    Trả về list[float] để lưu trực tiếp vào trường dense_vector trong Elasticsearch.
    """
    if not text or not str(text).strip():
        return []

    try:
        client = _get_genai_client()
        resp = await client.aio.models.embed_content(
            model="gemini-embedding-001",
            contents=str(text),
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        if getattr(resp, "embeddings", None):
            emb0 = resp.embeddings[0]
            return getattr(emb0, "values", None) or getattr(emb0, "embedding", None) or []
    except Exception as e:
        print(f"[EMBED] Lỗi khi tạo embedding cho tên '{text}': {e}")
    return []

async def index_single_document(es_client: Elasticsearch, index_name: str, customer_id: str, doc_id: str, doc_body: dict):
    """
    Nạp (hoặc ghi đè) một bản ghi duy nhất vào index chia sẻ với routing.
    """
    sanitized_customer_id = sanitize_for_es(customer_id)
    doc_body['customer_id'] = sanitized_customer_id
    sanitized_doc_id = sanitize_for_es(doc_id)
    composite_id = f"{sanitized_customer_id}_{sanitized_doc_id}"
    
    try:
        response = await es_client.index(
            index=index_name,
            id=composite_id,
            document=doc_body,
            routing=sanitized_customer_id,
            refresh=True
        )
        return response
    except Exception as e:
        raise IOError(f"Lỗi khi nạp bản ghi đơn: {e}")


async def upsert_document_with_name_embedding(
    es_client: Elasticsearch,
    index_name: str,
    customer_id: str,
    doc_id: str,
    doc_body: dict,
    name_field: str,
):
    """Tạo mới hoặc cập nhật một document kèm vector embedding cho trường tên.

    - Nếu document đã tồn tại và tên KHÔNG đổi → giữ nguyên embedding cũ.
    - Nếu document mới hoặc tên thay đổi → tạo embedding mới bằng Google Gemini.
    """

    sanitized_customer_id = sanitize_for_es(customer_id)
    sanitized_doc_id = sanitize_for_es(doc_id)
    composite_id = f"{sanitized_customer_id}_{sanitized_doc_id}"

    existing_source: Dict[str, Any] | None = None
    try:
        existing = await es_client.get(
            index=index_name,
            id=composite_id,
            routing=sanitized_customer_id,
        )
        if existing and existing.get("found"):
            existing_source = existing.get("_source", {})
    except NotFoundError:
        # Document chưa tồn tại: để existing_source = None để tạo mới
        existing_source = None
    except Exception as e:
        # Các lỗi khác: log lại nhưng không chặn flow upsert
        print(f"[UPSERT] Lỗi khi kiểm tra document {composite_id}: {e}")
        existing_source = None

    new_name = doc_body.get(name_field)
    old_name = existing_source.get(name_field) if existing_source else None
    old_embedding = (
        existing_source.get(f"{name_field}_embedding") if existing_source else None
    )

    # Quyết định có cần re-embed hay không
    embedding = old_embedding
    try:
        if (new_name or "").strip() != (old_name or "").strip():
            embedding = await _embed_name_with_google(str(new_name) if new_name else "")
    except Exception as e:
        print(f"⚠️ Lỗi khi embed lại cho document {doc_id}: {e}")

    doc_body["customer_id"] = sanitized_customer_id
    if embedding is not None:
        doc_body[f"{name_field}_embedding"] = embedding

    try:
        response = await es_client.index(
            index=index_name,
            id=composite_id,
            document=doc_body,
            routing=sanitized_customer_id,
            refresh=True,
        )
        return response
    except Exception as e:
        raise IOError(f"Lỗi khi upsert bản ghi kèm embedding: {e}")

async def delete_single_document(es_client: Elasticsearch, index_name: str, customer_id: str, doc_id: str):
    """
    Xóa một bản ghi duy nhất khỏi index chia sẻ.
    """
    sanitized_customer_id = sanitize_for_es(customer_id)
    sanitized_doc_id = sanitize_for_es(doc_id)
    composite_id = f"{sanitized_customer_id}_{sanitized_doc_id}"
    try:
        response = await es_client.delete(
            index=index_name,
            id=composite_id,
            routing=sanitized_customer_id,
            refresh=True
        )
        return response
    except Exception as e:
        raise IOError(f"Lỗi khi xóa bản ghi: {e}")

async def bulk_index_documents(es_client: Elasticsearch, index_name: str, customer_id: str, documents: list[dict], id_field: str):
    """
    Nạp hàng loạt một danh sách các bản ghi vào index chia sẻ.
    Hàm này không xóa dữ liệu cũ.
    """
    actions = []
    sanitized_customer_id = sanitize_for_es(customer_id)
    
    for doc in documents:
        doc_id = doc.get(id_field)
        if not doc_id:
            continue 

        sanitized_doc_id = sanitize_for_es(doc_id)
        composite_id = f"{sanitized_customer_id}_{sanitized_doc_id}"
        doc['customer_id'] = sanitized_customer_id
        
        action = {
            "_index": index_name,
            "_id": composite_id,
            "_source": doc,
            "routing": sanitized_customer_id
        }
        actions.append(action)

    if not actions:
        return 0, 0

    try:
        success, failed = await async_bulk(es_client, actions, raise_on_error=False, refresh=True)
        return success, failed
    except Exception as e:
        raise IOError(f"Lỗi trong quá trình bulk indexing hàng loạt: {e}")

async def process_and_upsert_file_data(
    es_client: Elasticsearch,
    customer_id: str,
    index_name: str,
    file_content: bytes,
    columns_config: dict
):
    """
    Đọc file Excel, xử lý và NẠP THÊM (upsert) dữ liệu vào index chia sẻ.
    Hàm này KHÔNG xóa dữ liệu cũ của khách hàng.
    """
    try:
        df = pd.read_excel(io.BytesIO(file_content))
        
        config_cols = columns_config.get('names', [])
        rename_map = columns_config.get('rename_map', {})

        missing_cols = [col for col in config_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Các cột sau không tìm thấy trong file Excel: {', '.join(missing_cols)}")

        df = df[config_cols]
        
        for col in columns_config.get('required', []):
            if pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].str.strip()
            df[col] = df[col].replace(r'^\s*$', np.nan, regex=True)

        df = df.dropna(subset=columns_config['required'])

        for col, dtype in columns_config.get('numerics', {}).items():
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).astype(dtype)
        
        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        df = df.where(pd.notnull(df), None).replace({np.nan: None})
    except Exception as e:
        raise ValueError(f"Lỗi đọc hoặc xử lý file Excel: {e}")

    documents = df.to_dict('records')
    if not documents:
        return 0, 0
    
    id_generation_field = columns_config.get('id_generation_field')
    renamed_id_gen_field = rename_map.get(id_generation_field, id_generation_field)
    renamed_id_field = None

    if id_generation_field and renamed_id_gen_field in documents[0]:
        if index_name == FAQ_INDEX:
            for doc in documents:
                question = doc.get(renamed_id_gen_field, '')
                if question and isinstance(question, str):
                    doc['faq_id'] = hashlib.sha1(question.strip().lower().encode('utf-8')).hexdigest()
                else:
                    doc['faq_id'] = None
            renamed_id_field = 'faq_id'

    if not renamed_id_field:
        original_id_field = columns_config.get('id_field')
        renamed_id_field = rename_map.get(original_id_field, original_id_field)

    if index_name == FAQ_INDEX:
        for document in documents:
            document['created_at'] = datetime.now(timezone.utc)

    success, failed = await bulk_index_documents(
        es_client,
        index_name,
        customer_id,
        documents,
        id_field=renamed_id_field
    )
    return success, failed

async def process_and_upsert_file_data_with_embedding(
    es_client: Elasticsearch,
    customer_id: str,
    index_name: str,
    file_content: bytes,
    columns_config: dict,
    embed_name_field: str,
    name_field: str,
):
    """Đọc file Excel và UP SERT từng dòng bằng upsert_document_with_name_embedding.

    - KHÔNG xóa dữ liệu cũ của customer.
    - Chỉ re-embed khi trường tên (name_field) thay đổi.
    - embed_name_field là tên cột SAU khi rename (ví dụ: 'model', 'ten_dich_vu', 'accessory_name').
    """

    try:
        df = pd.read_excel(io.BytesIO(file_content))

        config_cols = columns_config.get("names", [])
        rename_map = columns_config.get("rename_map", {})

        missing_cols = [col for col in config_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(
                f"Các cột sau không tìm thấy trong file Excel: {', '.join(missing_cols)}"
            )

        df = df[config_cols]

        for col in columns_config.get("required", []):
            if pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].str.strip()
            df[col] = df[col].replace(r"^\s*$", np.nan, regex=True)

        df = df.dropna(subset=columns_config["required"])

        for col, dtype in columns_config.get("numerics", {}).items():
            if dtype == float:
                df[col] = (
                    pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
                    .fillna(0)
                    .astype(float)
                )
            elif dtype == int:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        df = df.where(pd.notnull(df), None).replace({np.nan: None})
    except Exception as e:
        raise ValueError(f"Lỗi đọc hoặc xử lý file Excel: {e}")

    documents = df.to_dict("records")
    if not documents:
        return 0, 0

    original_id_field = columns_config.get("id_field")
    renamed_id_field = columns_config.get("rename_map", {}).get(
        original_id_field, original_id_field
    )

    sanitized_customer_id = sanitize_for_es(customer_id)
    success = 0
    failed_items: list[dict[str, Any]] = []

    for doc in documents:
        doc_id = doc.get(renamed_id_field)
        if not doc_id:
            failed_items.append({"id": None, "error": f"Thiếu '{renamed_id_field}'."})
            continue

        try:
            # upsert_document_with_name_embedding sẽ tự xử lý re-embed khi tên đổi
            await upsert_document_with_name_embedding(
                es_client=es_client,
                index_name=index_name,
                customer_id=sanitized_customer_id,
                doc_id=str(doc_id),
                doc_body=doc,
                name_field=name_field,
            )
            success += 1
        except Exception as item_e:
            failed_items.append({"id": str(doc_id), "error": str(item_e)})

    return success, failed_items

async def delete_documents_by_customer(
    es_client: Elasticsearch, 
    index_name: str, 
    customer_id: str
):
    """
    Xóa tất cả các document của một customer_id cụ thể khỏi một index.
    """
    query = {
        "query": {
            "term": {
                "customer_id": customer_id
            }
        }
    }
    try:
        response = await es_client.delete_by_query(
            index=index_name,
            body=query,
            refresh=True,
            routing=customer_id
        )
        return response.body
    except Exception as e:
        print(f"Lỗi khi xóa document cho customer_id '{customer_id}' trong index '{index_name}': {e}")
        raise

async def bulk_delete_documents(
    es_client: AsyncElasticsearch,
    index_name: str,
    customer_id: str,
    doc_ids: List[str],
    id_field: str
) -> Dict[str, Any]:
    """
    Xóa hàng loạt các document từ một index dựa trên danh sách ID và một trường cụ thể.
    """
    if not doc_ids:
        return {"deleted": 0, "failures": []}

    query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"customer_id": customer_id}},
                    {"terms": {id_field: doc_ids}}
                ]
            }
        }
    }
    try:
        response = await es_client.delete_by_query(
            index=index_name,
            body=query,
            refresh=True,
            routing=customer_id
        )
        return response.body
    except Exception as e:
        print(f"Lỗi khi xóa hàng loạt document cho customer_id '{customer_id}' trong index '{index_name}': {e}")
        raise