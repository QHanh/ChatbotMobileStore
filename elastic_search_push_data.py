import os
import pandas as pd
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import warnings
from dotenv import load_dotenv
# from sentence_transformers import SentenceTransformer  # 👉 BỎ COMMENT nếu cần tạo embedding
import numpy as np
import json

load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

# --- CẤU HÌNH ---
ELASTIC_HOST = "http://localhost:9200"
INDEX_NAME = "iphone_products"
XLSX_FILE_PATH = "iPhone.xlsm"

# --- KẾT NỐI ---
try:
    es_client = Elasticsearch(hosts=[ELASTIC_HOST])
    if not es_client.ping():
        raise ConnectionError("Không thể kết nối đến Elasticsearch.")
    print("✅ Kết nối đến Elasticsearch thành công!")
except (ValueError, ConnectionError) as e:
    print(f"❌ Lỗi: {e}")
    exit()

def create_index_mapping():
    if es_client.indices.exists(index=INDEX_NAME):
        print(f"⚠️  Index '{INDEX_NAME}' đã tồn tại. Xóa index cũ để tạo lại.")
        es_client.indices.delete(index=INDEX_NAME)

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
            
            # 👉 Nếu cần bật tìm kiếm ngữ nghĩa, bỏ comment bên dưới
            # "text_embedding": {
            #     "type": "dense_vector",
            #     "dims": 384
            # }
        }
    }

    print(f"🛠 Tạo index mới '{INDEX_NAME}' với mapping...")
    es_client.indices.create(index=INDEX_NAME, mappings=mapping)
    print("✅ Tạo index thành công.")

def process_and_index_data():
    try:
        df = pd.read_excel(XLSX_FILE_PATH, sheet_name='TONGHOP')
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
        print(f"❌ Lỗi: Không tìm thấy file '{XLSX_FILE_PATH}'.")
        return
    except Exception as e:
        print(f"❌ Lỗi khi đọc file Excel: {e}")
        return

    # 📦 Nếu cần dùng embedding, bỏ comment bên dưới
    # print("📦 Đang tải model embedding...")
    # embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    # print("✅ Tải model thành công.")

    actions = []
    total_rows = len(df)

    for index, row in df.iterrows():
        print(f"➡️  Đang xử lý dòng {index + 1}/{total_rows}: {row['model']}")

        # Ép toàn bộ NaN → None để đảm bảo JSON hợp lệ
        doc = json.loads(json.dumps(row.to_dict(), default=lambda x: None))

        # --- TẠO VECTOR EMBEDDING CHO TÌM KIẾM NGỮ NGHĨA ---
        # 👉 Bỏ comment nếu cần tạo text_embedding
        # text_to_embed = f"Điện thoại {doc.get('model', '')} màu {doc.get('mau_sac', '')} dung lượng {doc.get('dung_luong', '')}. " \
        #               f"Thông số camera: {doc.get('camera', '')}. " \
        #               f"Thông số pin: {doc.get('pin_mah', '')}. " \
        #               f"Chip và RAM: {doc.get('chip_ram', '')}."

        # doc['text_embedding'] = embedding_model.encode(text_to_embed).tolist()

        action = {
            "_index": INDEX_NAME,
            "_id": doc['ma_san_pham'] + "_" + str(doc['ton_kho']),  # tạo ID duy nhất
            "_source": doc
        }
        actions.append(action)

    print(f"\n🚀 Đang index {len(actions)} sản phẩm...")
    try:
        success, failed = bulk(es_client, actions, raise_on_error=False)
        print(f"✅ Index thành công: {success} sản phẩm.")
        if failed:
            print(f"❌ Index thất bại: {len(failed)} sản phẩm.")
            for i, fail_info in enumerate(failed[:5]):
                error = fail_info.get('index', {}).get('error', {})
                print(f"  ❌ Lỗi {i+1}: {error.get('type', 'unknown')} - {error.get('reason', 'no reason')}")
    except Exception as e:
        print(f"❌ Đã xảy ra lỗi khi index dữ liệu: {e}")

if __name__ == "__main__":
    create_index_mapping()
    process_and_index_data()
    print("\n✅ Quá trình xử lý và index dữ liệu đã hoàn tất.")
