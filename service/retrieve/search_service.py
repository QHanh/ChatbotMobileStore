from elasticsearch import AsyncElasticsearch
from typing import Optional, List, Dict, Any
from service.data.data_loader_elastic_search import PRODUCTS_INDEX, SERVICES_INDEX, ACCESSORIES_INDEX
from service.utils.helpers import sanitize_for_es

async def search_products(
    es_client: AsyncElasticsearch,
    customer_id: str,
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    loai_thiet_bi: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm sản phẩm trong index 'products' chia sẻ, lọc theo customer_id.
    """
    if not es_client:
        return [{"error": "Không thể kết nối đến Elasticsearch."}]

    sanitized_customer_id = sanitize_for_es(customer_id)
    query = {"bool": {"must": [], "should": [], "filter": []}}
    
    query["bool"]["filter"].append({"term": {"customer_id": sanitized_customer_id}})
    
    if model:
        query["bool"]["must"].append({
            "bool": {
                "should": [
                    {"term": {"model.keyword": {"value": model, "boost": 3.0}}},
                    {"match_phrase": {"model": {"query": model, "boost": 2.0}}},
                    {"match": {"model": model}}
                ]
            }
        })

    if mau_sac: query["bool"]["must"].append({"match": {"mau_sac": mau_sac}})
    if loai_thiet_bi: query["bool"]["should"].append({"match": {"loai_thiet_bi": loai_thiet_bi}})
    if dung_luong: query["bool"]["must"].append({"match": {"dung_luong": dung_luong}})
    if tinh_trang_may: query["bool"]["should"].append({"match": {"tinh_trang_may": tinh_trang_may}})
    
    price_range = {}
    if min_gia is not None: price_range["gte"] = min_gia
    if max_gia is not None: price_range["lte"] = max_gia
    if price_range: query["bool"]["filter"].append({"range": {"gia": price_range}})

    try:
        response = await es_client.search(
            index=PRODUCTS_INDEX,
            query=query,
            routing=sanitized_customer_id,
            size=10
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        print(f"Tìm thấy {len(hits)} sản phẩm phù hợp cho khách hàng '{customer_id}'.")
        return hits
    except Exception as e:
        print(f"Lỗi khi tìm kiếm sản phẩm: {e}")
        return [{"error": f"Lỗi tìm kiếm: {e}"}]

async def search_services(
    es_client: AsyncElasticsearch,
    customer_id: str,
    ten_dich_vu: Optional[str] = None,
    ten_san_pham: Optional[str] = None,
    loai_dich_vu: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm dịch vụ trong index 'services' chia sẻ, lọc theo customer_id.
    """
    if not es_client:
        return [{"error": "Không thể kết nối đến Elasticsearch."}]

    sanitized_customer_id = sanitize_for_es(customer_id)
    query = {"bool": {"must": [], "should": [], "filter": []}}
    query["bool"]["filter"].append({"term": {"customer_id": sanitized_customer_id}})

    if ten_dich_vu:
        query["bool"]["must"].append({"match": {"ten_dich_vu": {"query": ten_dich_vu}}})
        query["bool"]["should"].append({"match_phrase": {"ten_dich_vu": {"query": ten_dich_vu, "boost": 10.0}}})
    
    if ten_san_pham: query["bool"]["filter"].append({"term": {"ten_san_pham.keyword": {"value": ten_san_pham}}})

    if loai_dich_vu:
        query["bool"]["should"].append({"match": {"loai_dich_vu": {"query": loai_dich_vu, "boost": 5.0}}})

    price_range = {}
    if min_gia is not None: price_range["gte"] = min_gia
    if max_gia is not None: price_range["lte"] = max_gia
    if price_range: query["bool"]["filter"].append({"range": {"gia": price_range}})

    try:
        response = await es_client.search(
            index=SERVICES_INDEX,
            query=query,
            routing=sanitized_customer_id,
            size=10
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        if hits:
            print(f"Tìm thấy {len(hits)} dịch vụ phù hợp cho khách hàng '{customer_id}'.")
            return hits

        search_terms: List[str] = []
        for term in [ten_dich_vu, ten_san_pham, loai_dich_vu]:
            if term:
                search_terms.append(str(term))

        if search_terms:
            combined_query = " ".join(search_terms)
            fallback_query = {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": combined_query,
                            "fields": ["ten_dich_vu^3", "ten_san_pham", "loai_dich_vu^2"],
                            "fuzziness": "AUTO"
                        }
                    },
                    "filter": [
                        {"term": {"customer_id": customer_id}}
                    ]
                }
            }
            response = await es_client.search(
                index=SERVICES_INDEX,
                query=fallback_query,
                routing=sanitized_customer_id,
                size=10
            )
            hits = [hit['_source'] for hit in response['hits']['hits']]
            print(f"Fallback multi_match: tìm thấy {len(hits)} dịch vụ phù hợp.")
            return hits

        return []
    except Exception as e:
        print(f"Lỗi khi tìm kiếm dịch vụ: {e}")
        return [{"error": f"Lỗi tìm kiếm: {e}"}]

async def search_accessories(
    es_client: AsyncElasticsearch,
    customer_id: str,
    ten_phu_kien: Optional[str] = None,
    phan_loai_phu_kien: Optional[str] = None,
    thuoc_tinh_phu_kien: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm phụ kiện trong index 'accessories' chia sẻ, lọc theo customer_id.
    """
    if not es_client:
        return [{"error": "Không thể kết nối đến Elasticsearch."}]

    sanitized_customer_id = sanitize_for_es(customer_id)
    query = {"bool": {"must": [], "should": [], "filter": []}}
    query["bool"]["filter"].append({"term": {"customer_id": sanitized_customer_id}})

    if ten_phu_kien:
        query["bool"]["must"].append({"match": {"accessory_name": {"query": ten_phu_kien}}})
        query["bool"]["should"].append({"match_phrase": {"accessory_name": {"query": ten_phu_kien, "boost": 10.0}}})

    if phan_loai_phu_kien:
        query["bool"]["should"].append({
            "bool": {
                "should": [
                    {"match": {"category": {"query": phan_loai_phu_kien, "boost": 5.0}}}
                ]
            }
        })
    
    if thuoc_tinh_phu_kien:
        query["bool"]["should"].append({"match": {"properties": {"query": thuoc_tinh_phu_kien, "operator": "and"}}})

    price_range = {}
    if min_gia is not None: price_range["gte"] = min_gia
    if max_gia is not None: price_range["lte"] = max_gia
    if price_range: query["bool"]["filter"].append({"range": {"lifecare_price": price_range}})

    try:
        response = await es_client.search(
            index=ACCESSORIES_INDEX,
            query=query,
            routing=sanitized_customer_id,
            size=10
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        print(f"Tìm thấy {len(hits)} phụ kiện phù hợp cho khách hàng '{customer_id}'.")
        return hits

    except Exception as e:
        print(f"Lỗi khi tìm kiếm phụ kiện: {e}")
        return [{"error": f"Lỗi tìm kiếm: {e}"}]

if __name__ == '__main__':
    import asyncio

    async def main():
        es_client_mock = AsyncElasticsearch()
        results = await search_products(es_client_mock, customer_id="customer123", model="iPhone 15 Pro Max", mau_sac="Titan Tự nhiên")
        if results:
            for product in results:
                print(f"- {product.get('model')} {product.get('dung_luong')} {product.get('mau_sac')}, Giá: {product.get('gia'):,.0f}đ")

    asyncio.run(main())
