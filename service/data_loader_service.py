import pandas as pd
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import numpy as np
import json
import warnings
import io

warnings.filterwarnings("ignore", category=UserWarning)

def create_product_index(es_client: Elasticsearch, index_name: str):
    """
    Tạo index mới trong Elasticsearch với mapping cho sản phẩm của khách hàng.
    Nếu index đã tồn tại, nó sẽ bị xóa và tạo lại.
    """
    if es_client.indices.exists(index=index_name):
        print(f"⚠️ Index '{index_name}' đã tồn tại. Đang xóa index cũ.")
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

    print(f"🛠 Đang tạo index '{index_name}' với mapping...")
    es_client.indices.create(index=index_name, mappings=mapping)
    print("✅ Thành công tạo index.")

def process_and_index_product_data(es_client: Elasticsearch, index_name: str, file_content: bytes):
    """
    Đọc dữ liệu sản phẩm từ nội dung file Excel, xử lý và tạo index trong Elasticsearch.
    """
    try:
        df = pd.read_excel(io.BytesIO(file_content), sheet_name='TONGHOP')
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

    except Exception as e:
        raise Exception(f"Error reading Excel content: {e}")

    actions = []
    total_rows = len(df)

    for index, row in df.iterrows():
        print(f"➡️ Đang xử lý dòng {index + 1}/{total_rows}: {row['model']}")
        doc = json.loads(json.dumps(row.to_dict(), default=lambda x: None))

        action = {
            "_index": index_name,
            "_id": doc['ma_san_pham'] + "_" + str(doc['ton_kho']),
            "_source": doc
        }
        actions.append(action)

    print(f"\n🚀 Đang tạo index {len(actions)} sản phẩm...")
    try:
        success, failed = bulk(es_client, actions, raise_on_error=False)
        print(f"✅ Thành công tạo index: {success} sản phẩm.")
        if failed:
            print(f"❌ Thất bại tạo index: {len(failed)} sản phẩm.")
            for i, fail_info in enumerate(failed[:5]):
                error = fail_info.get('index', {}).get('error', {})
                print(f"  - Error {i+1}: {error.get('type', 'unknown')} - {error.get('reason', 'no reason')}")
        return success, len(failed)
    except Exception as e:
        raise Exception(f"Lỗi xảy ra trong quá trình tạo index: {e}")
    
def create_service_index(es_client: Elasticsearch, index_name: str):
    """
    Tạo index mới trong Elasticsearch với mapping cho dịch vụ của khách hàng.
    Nếu index đã tồn tại, nó sẽ bị xóa và tạo lại.
    """
    if es_client.indices.exists(index=index_name):
        print(f"⚠️ Index '{index_name}' đã tồn tại. Đang xóa index cũ.")
        es_client.indices.delete(index=index_name)

    mapping = {
        "properties": {
            "ma_dich_vu": {"type": "keyword"},
            "ten_dich_vu": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "ten_san_pham": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "chi_tiet_dich_vu": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "gia": {"type": "keyword"},
            "bao_hanh": {"type": "keyword"},
            "thoi_gian_thuc_hien": {"type": "keyword"},
            "ghi_chu": {"type": "text"},
        }
    }

    print(f"🛠 Đang tạo index '{index_name}' với mapping...")
    es_client.indices.create(index=index_name, mappings=mapping)
    print("✅ Thành công tạo index.")

def process_and_index_service_data(es_client: Elasticsearch, index_name: str, file_content: bytes):
    """
    Đọc dữ liệu dịch vụ từ nội dung file Excel, xử lý và tạo index trong Elasticsearch.
    """
    try:
        df = pd.read_excel(io.BytesIO(file_content), sheet_name='DICHVU')
        df.columns = [
            'ma_dich_vu', 'ten_dich_vu', 'ten_san_pham', 'chi_tiet_dich_vu', 'gia', 'bao_hanh', 'thoi_gian_thuc_hien', 'ghi_chu'
        ]
        df = df.dropna(subset=['ma_dich_vu', 'ten_dich_vu'])
        df['gia'] = pd.to_numeric(df['gia'], errors='coerce').fillna(0).astype(float)
    except Exception as e:
        raise Exception(f"Error reading Excel content: {e}")
    
    actions = []
    total_rows = len(df)

    for index, row in df.iterrows():
        print(f"➡️ Đang xử lý dòng {index + 1}/{total_rows}: {row['ten_dich_vu']}")
        doc = json.loads(json.dumps(row.to_dict(), default=lambda x: None))

        action = {
            "_index": index_name,
            "_id": doc['ma_dich_vu'],
            "_source": doc
        }
        actions.append(action)

    print(f"\n🚀 Đang tạo index {len(actions)} dịch vụ...")
    try:
        success, failed = bulk(es_client, actions, raise_on_error=False)
        print(f"✅ Thành công tạo index: {success} dịch vụ.")
        if failed:
            print(f"❌ Thất bại tạo index: {len(failed)} dịch vụ.")
            for i, fail_info in enumerate(failed[:5]):
                error = fail_info.get('index', {}).get('error', {})
                print(f"  - Error {i+1}: {error.get('type', 'unknown')} - {error.get('reason', 'no reason')}")
        return success, len(failed)
    except Exception as e:
        raise Exception(f"Lỗi xảy ra trong quá trình tạo index: {e}")