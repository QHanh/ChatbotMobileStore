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
        query["bool"]["must"].append({"match": {"model": {"query": model, "boost": 2}}})
    
    if mau_sac:
        query["bool"]["filter"].append({"term": {"mau_sac": mau_sac}})

    if loai_thiet_bi:
        query["bool"]["filter"].append({"match": {"loai_thiet_bi": loai_thiet_bi}})
        
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
    mau_sac_san_pham: Optional[str] = None,
    loai_dich_vu: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
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
    
    if mau_sac_san_pham:
        query["bool"]["must"].append({"match": {"mau_sac_san_pham": mau_sac_san_pham}})
    
    if loai_dich_vu:
        query["bool"]["must"].append({"match": {"loai_dich_vu": loai_dich_vu}})
    
    price_range = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia
    if price_range:
        query["bool"]["filter"].append({"range": {"gia": price_range}})
    
    try:
        response = es.search(index=index_name, query=query, size=10)
        hits = [hit['_source'] for hit in response['hits']['hits']]
        if hits:
            print(f"Tìm thấy {len(hits)} dịch vụ phù hợp (theo bộ lọc cụ thể).")
            return hits

        # Fallback: multi_match trên các cột văn bản nếu không tìm thấy kết quả
        search_terms: List[str] = []
        for term in [ten_dich_vu, ten_san_pham, hang_san_pham, mau_sac_san_pham, loai_dich_vu]:
            if term:
                search_terms.append(str(term))

        if search_terms:
            combined_query = " ".join(search_terms)
            fallback_query = {
                "multi_match": {
                    "query": combined_query,
                    "type": "most_fields",
                    "fields": [
                        "ten_dich_vu^3",
                        "loai_dich_vu^2",
                        "hang_san_pham",
                        "mau_sac_san_pham",
                        "ten_san_pham",
                        "ghi_chu"
                    ],
                    "fuzziness": "AUTO"
                }
            }
            response = es.search(index=index_name, query=fallback_query, size=10)
            hits = [hit['_source'] for hit in response['hits']['hits']]
            print(f"Fallback multi_match: tìm thấy {len(hits)} dịch vụ phù hợp.")
            return hits

        # Không có tham số nào để fallback
        print("Không có tham số tìm kiếm để thực hiện fallback multi_match.")
        return []
    except Exception as e:
        print(f"Lỗi khi tìm kiếm trong Elasticsearch: {e}")
        return [{"error": f"Lỗi khi tìm kiếm: {e}"}]
    
def search_accessories(
    index_name: str,
    ten_phu_kien: Optional[str] = None,
    thuoc_tinh_phu_kien: Optional[str] = None,
    loai_phu_kien: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm phụ kiện trong Elasticsearch dựa trên các tiêu chí lọc.
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
    
    if ten_phu_kien:
        query["bool"]["must"].append({"match": {"ten_phu_kien": ten_phu_kien}})
    
    if thuoc_tinh_phu_kien:
        query["bool"]["must"].append({"match": {"thuoc_tinh_phu_kien": thuoc_tinh_phu_kien}})
    
    if loai_phu_kien:
        query["bool"]["must"].append({"match": {"loai_phu_kien": loai_phu_kien}})
    
    price_range = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia
    if price_range:
        query["bool"]["filter"].append({"range": {"gia": price_range}})
    
    try:
        response = es.search(index=index_name, query=query, size=10)
        hits = [hit['_source'] for hit in response['hits']['hits']]
        if hits:
            print(f"Tìm thấy {len(hits)} phụ kiện phù hợp (theo bộ lọc cụ thể).")
            return hits
        
        # Fallback: multi_match trên các cột văn bản nếu không tìm thấy kết quả
        search_terms: List[str] = []
        for term in [ten_phu_kien, thuoc_tinh_phu_kien, loai_phu_kien]:
            if term:
                search_terms.append(str(term))

        if search_terms:
            combined_query = " ".join(search_terms)
            fallback_query = {
                "multi_match": {
                    "query": combined_query,
                    "type": "most_fields",
                    "fields": [
                        "ten_phu_kien^3",
                        "thuoc_tinh_phu_kien^2",
                        "loai_phu_kien",
                    ],
                    "fuzziness": "AUTO"
                }
            }
            response = es.search(index=index_name, query=fallback_query, size=10)
            hits = [hit['_source'] for hit in response['hits']['hits']]
            print(f"Fallback multi_match: tìm thấy {len(hits)} phụ kiện phù hợp.")
            return hits

        # Không có tham số nào để fallback
        print("Không có tham số tìm kiếm để thực hiện fallback multi_match.")
        return []
    except Exception as e:
        print(f"Lỗi khi tìm kiếm trong Elasticsearch: {e}")
        return [{"error": f"Lỗi khi tìm kiếm: {e}"}]

if __name__ == '__main__':
    results = search_products(index_name="iphone_products", model="iPhone 15 Pro Max", mau_sac="Titan Tự nhiên")
    if results:
        for product in results:
            print(f"- {product.get('model')} {product.get('dung_luong')} {product.get('mau_sac')}, Giá: {product.get('gia'):,.0f}đ")
