import os
from elasticsearch import Elasticsearch
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from config.settings import ELASTIC_HOST

load_dotenv()

es_client = None

def get_es_client():
    """
    Initializes and returns a single instance of the Elasticsearch client.
    """
    global es_client
    if es_client is None:
        try:
            es_client = Elasticsearch(hosts=[ELASTIC_HOST])
            if not es_client.ping():
                raise ConnectionError("Không thể kết nối đến Elasticsearch.")
            print("search_service: Kết nối đến Elasticsearch thành công!")
        except ConnectionError as e:
            print(f"Lỗi trong search_service: {e}")
            es_client = None
    return es_client

def search_products(
    index_name: str,
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    loai_thiet_bi: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm sản phẩm iPhone trong Elasticsearch dựa trên các tiêu chí lọc.

    Args:
        model (Optional[str]): Tên model iPhone (ví dụ: "iPhone 15 Pro Max").
        mau_sac (Optional[str]): Màu sắc của sản phẩm.
        dung_luong (Optional[str]): Dung lượng lưu trữ (ví dụ: "256GB").
        tinh_trang_may (Optional[str]): Tình trạng của máy (ví dụ: "trầy xước").
        loai_thiet_bi (Optional[str]): Loại thiết bị (ví dụ: "Cũ", "Mới").
        min_gia (Optional[float]): Mức giá tối thiểu.
        max_gia (Optional[float]): Mức giá tối đa.

    Returns:
        List[Dict[str, Any]]: Danh sách các sản phẩm phù hợp.
    """
    es = get_es_client()
    if not es:
        return [{"error": "Không thể kết nối đến Elasticsearch."}]

    query = {
        "bool": {
            "must": [],
            "should": [],
            "filter": []
        }
    }

    if model:
        # Use 'match' for full-text search on the model name, which is more flexible.
        query["bool"]["must"].append({"match": {"model": {"query": model, "boost": 2}}})
    
    if mau_sac:
        # 'term' is good for exact matches on keywords like color.
        query["bool"]["filter"].append({"term": {"mau_sac": mau_sac}})

    if loai_thiet_bi:
        query["bool"]["filter"].append({"term": {"loai_thiet_bi": loai_thiet_bi}})
        
    if dung_luong:
        query["bool"]["filter"].append({"term": {"dung_luong": dung_luong}})
        
    if tinh_trang_may:
        query["bool"]["should"].append({"match": {"tinh_trang_may": tinh_trang_may}})
    
    price_range = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia
    if price_range:
        query["bool"]["filter"].append({"range": {"gia": price_range}})

    query["bool"]["filter"].append({"range": {"ton_kho": {"gt": 0}}})

    try:
        response = es.search(
            index=index_name,
            query=query,
            size=10
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        print(f"Tìm thấy {len(hits)} sản phẩm phù hợp.")
        return hits
    except Exception as e:
        print(f"Lỗi khi tìm kiếm trong Elasticsearch: {e}")
        return [{"error": f"Lỗi khi tìm kiếm: {e}"}]

def search_services(
    index_name: str,
    ten_dich_vu: Optional[str] = None,
    ten_san_pham: Optional[str] = None,
    hang_san_pham: Optional[str] = None,
    hang_dich_vu: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm dịch vụ trong Elasticsearch dựa trên các tiêu chí lọc.
    Args:
        ten_dich_vu (Optional[str]): Tên dịch vụ (ví dụ: "Thay pin").
        ten_san_pham (Optional[str]): Tên sản phẩm đi kèm (ví dụ: "iPhone 15 Pro Max").
        chi_tiet_dich_vu (Optional[str]): Chi tiết dịch vụ (ví dụ: "Pin Lithium").
    """
    es = get_es_client()
    if not es:
        return [{"error": "Không thể kết nối đến Elasticsearch."}]
    
    query = {
        "bool": {
            "must": [],
            "should": [],
            "filter": []
        }
    }
    
    if ten_dich_vu: 
        query["bool"]["must"].append({"match": {"ten_dich_vu": ten_dich_vu}})
    
    if hang_san_pham:
        query["bool"]["must"].append({"match": {"hang_san_pham": hang_san_pham}})
    
    if ten_san_pham:
        query["bool"]["must"].append({"match": {"ten_san_pham": ten_san_pham}})
    
    if hang_dich_vu:
        query["bool"]["must"].append({"match": {"hang_dich_vu": hang_dich_vu}})
    
    try:
        response = es.search(
            index=index_name,
            query=query,
            size=10
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        print(f"Tìm thấy {len(hits)} dịch vụ phù hợp.")
        return hits
    except Exception as e:
        print(f"Lỗi khi tìm kiếm trong Elasticsearch: {e}")
        return [{"error": f"Lỗi khi tìm kiếm: {e}"}]
    

if __name__ == '__main__':
    results = search_products(index_name="iphone_products", model="iPhone 15 Pro Max", mau_sac="Titan Tự nhiên")
    if results:
        for product in results:
            print(f"- {product.get('model')} {product.get('dung_luong')} {product.get('mau_sac')}, Giá: {product.get('gia'):,.0f}đ")
