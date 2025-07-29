import pandas as pd
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import numpy as np
import json
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

def create_customer_index(es_client: Elasticsearch, index_name: str):
    """
    Creates a new Elasticsearch index with a specific mapping for customer products.
    If the index already exists, it's deleted and recreated.
    """
    if es_client.indices.exists(index=index_name):
        print(f"⚠️ Index '{index_name}' already exists. Deleting old index.")
        es_client.indices.delete(index=index_name)

    mapping = {
        "properties": {
            "ma_san_pham": {"type": "keyword"},
            "model": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "mau_sac": {"type": "keyword"},
            "dung_luong": {"type": "keyword"},
            "bao_hanh": {"type": "keyword"},
            "tinh_trang_may": {"type": "keyword"},
            "tinh_trang_pin": {"type": "float"},
            "gia": {"type": "double"},
            "ton_kho": {"type": "integer"},
            "ghi_chu": {"type": "text"},
            "ra_mat": {"type": "text"},
            "man_hinh": {"type": "text"},
            "chip_ram": {"type": "text"},
            "camera": {"type": "text"},
            "pin_mah": {"type": "text"},
            "ket_noi_hdh": {"type": "text"},
            "mau_sac_tieng_anh": {"type": "text"},
            "mau_sac_available": {"type": "text"},
            "dung_luong_available": {"type": "text"},
            "kich_thuoc_trong_luong": {"type": "text"},
        }
    }

    print(f"🛠 Creating new index '{index_name}' with mapping...")
    es_client.indices.create(index=index_name, mappings=mapping)
    print("✅ Index created successfully.")

def process_and_index_data(es_client: Elasticsearch, index_name: str, file_stream):
    """
    Reads product data from an Excel file stream, processes it, and indexes it into Elasticsearch.
    """
    try:
        df = pd.read_excel(file_stream, sheet_name='TONGHOP')
        df.columns = [
            'ma_san_pham', 'model', 'mau_sac', 'dung_luong', 'bao_hanh',
            'tinh_trang_may', 'tinh_trang_pin', 'gia', 'ton_kho', 'ghi_chu',
            'ra_mat', 'man_hinh', 'chip_ram', 'camera', 'pin_mah', 'ket_noi_hdh',
            'mau_sac_tieng_anh', 'mau_sac_available', 'dung_luong_available',
            'kich_thuoc_trong_luong', 'bao_hanh_2'
        ]
        if 'bao_hanh_2' in df.columns:
            df = df.drop(columns=['bao_hanh_2'])

        df = df.dropna(subset=['ma_san_pham', 'model'])

        df['ton_kho'] = pd.to_numeric(df['ton_kho'], errors='coerce').fillna(0).astype(int)
        df['gia'] = pd.to_numeric(df['gia'], errors='coerce').fillna(0).astype(float)
        df['tinh_trang_pin'] = pd.to_numeric(df['tinh_trang_pin'], errors='coerce').fillna(0).astype(float)

        df['mau_sac'] = df['mau_sac'].astype(str).str.strip().str.title()

        df = df.where(pd.notnull(df), None).replace({np.nan: None})

    except FileNotFoundError:
        raise Exception(f"Error: Could not read the provided file stream.")
    except Exception as e:
        raise Exception(f"Error reading Excel file: {e}")

    actions = []
    total_rows = len(df)

    for index, row in df.iterrows():
        print(f"➡️ Processing row {index + 1}/{total_rows}: {row['model']}")
        doc = json.loads(json.dumps(row.to_dict(), default=lambda x: None))

        action = {
            "_index": index_name,
            "_id": doc['ma_san_pham'] + "_" + str(doc['ton_kho']),
            "_source": doc
        }
        actions.append(action)

    print(f"\n🚀 Indexing {len(actions)} products...")
    try:
        success, failed = bulk(es_client, actions, raise_on_error=False)
        print(f"✅ Successfully indexed: {success} products.")
        if failed:
            print(f"❌ Failed to index: {len(failed)} products.")
            for i, fail_info in enumerate(failed[:5]):
                error = fail_info.get('index', {}).get('error', {})
                print(f"  - Error {i+1}: {error.get('type', 'unknown')} - {error.get('reason', 'no reason')}")
        return success, len(failed)
    except Exception as e:
        raise Exception(f"An error occurred during bulk indexing: {e}") 