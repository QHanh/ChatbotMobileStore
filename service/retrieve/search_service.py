from elasticsearch import AsyncElasticsearch
from typing import Optional, List, Dict, Any
import json
import os
import aiohttp
from sqlalchemy.orm import Session
from database.database import CustomerIsSale, SessionLocal
from service.prompts.prompt_service import load_instructions
from service.data.data_loader_elastic_search import (
    PRODUCTS_INDEX,
    SERVICES_INDEX,
    ACCESSORIES_INDEX,
    FAQ_INDEX,
    _embed_name_with_google,
)
from service.utils.helpers import sanitize_for_es
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from google import genai
from google.genai import types

def _get_customer_is_sale(customer_id: str, thread_id: str) -> bool:
    """Kiểm tra xem thread có phải là của khách hàng mua buôn hay không."""
    if not thread_id:
        return False
    db: Session = SessionLocal()
    try:
        sale_status = db.query(CustomerIsSale).filter(
            CustomerIsSale.customer_id == customer_id,
            CustomerIsSale.thread_id == thread_id
        ).first()
        if sale_status:
            return sale_status.is_sale_customer
    finally:
        db.close()
    return False


async def filter_results_with_ai(
    query: str, 
    results: List[str],
    llm,
    chat_history: Optional[List[str]] = None
) -> List[str]:
    """Lọc kết quả tìm kiếm bằng AI để chọn ra những kết quả phù hợp nhất."""
    if not results:
        return []

    if not llm:
        print("LLM chưa được cung cấp, trả về kết quả gốc.")
        return results

    history_str = "\n".join(chat_history or [])
    results_str = "\n\n".join(results)
    db = SessionLocal()
    try:
        instr = load_instructions(db)
    finally:
        db.close()
    prompt_template_str = instr.get(
        "filter_results_prompt",
        """
            Bạn là một trợ lý AI có nhiệm vụ lọc kết quả tìm kiếm một cách nghiêm ngặt. Dựa trên LỊCH SỬ TRÒ CHUYỆN và CÂU HỎI HIỆN TẠI của người dùng, hãy lọc và chỉ giữ lại những kết quả tìm kiếm THỰC SỰ liên quan.

            **QUY TRÌNH LỌC:**
            1.  **Phân tích câu hỏi:** Xác định các **từ khóa chính** (thương hiệu, model/mã cụ thể, thuộc tính quan trọng).
            1b. **Phát hiện CỤM ĐẶC TRƯNG (brand + model/mã):** Ví dụ: "AIFEN A902", "RELIFE RL-056", "KAISI K-1205", "TX-50S". Cụm đặc trưng là sự kết hợp giữa thương hiệu/hãng và mã model/ký hiệu gồm chữ cái và/hoặc số.

            **ƯU TIÊN CHÍNH XÁC THEO CỤM ĐẶC TRƯNG:**
            -   Nếu câu hỏi có cụm đặc trưng D:
                -   GIỮ LẠI MỌI kết quả có chứa CHÍNH XÁC D (không phân biệt hoa thường, bỏ qua khoảng trắng và dấu gạch nối) trong tên hiển thị của kết quả, ví dụ dòng "Phụ kiện:" hoặc "Sản phẩm:", hoặc tổ hợp "Thương hiệu"+"mã".
                -   Các kết quả này được coi là PHÙ HỢP CHẮC CHẮN, không yêu cầu phải chứa thêm các từ khóa phụ khác.
                -   ĐẶT NHÓM kết quả khớp cụm đặc trưng lên TRƯỚC, giữ nguyên thứ tự xuất hiện ban đầu.
            -   Chỉ khi KHÔNG có kết quả nào khớp cụm đặc trưng, hãy áp dụng bước 2.

            2.  **Đối chiếu nghiêm ngặt:** So sánh từng kết quả với các từ khóa chính còn lại. Một kết quả CHỈ được coi là phù hợp nếu nó chứa **TẤT CẢ** các từ khóa chính mà người dùng đã nêu.
            
            **QUY TẮC XUẤT KẾT QUẢ:**
            -   Chỉ trả về các kết quả phù hợp sau khi đã lọc theo các quy tắc trên.
            -   Giữ nguyên định dạng ban đầu của các kết quả được chọn.
            -   Mỗi kết quả phải được phân tách bởi hai dấu xuống dòng.
            -   Nếu không có kết quả nào phù hợp, trả về một chuỗi rỗng.
            -   KHÔNG thêm bất kỳ lời giải thích, bình luận, hay tóm tắt nào.

            **DỮ LIỆU ĐẦU VÀO:**

            Lịch sử trò chuyện:
            {history}

            Câu hỏi của người dùng: "{query}"

            Danh sách kết quả tìm kiếm cần lọc:
            {results}
            """
    )

    try:
        filtered_results_str = ""
        use_langchain_fallback = False

        api_key = None
        try:
            if hasattr(llm, "google_api_key") and getattr(llm, "google_api_key"):
                secret = getattr(llm, "google_api_key")
                api_key = secret.get_secret_value() if hasattr(secret, "get_secret_value") else secret
        except Exception:
            api_key = None

        if api_key:
            print("Sử dụng Google GenAI SDK để lọc kết quả.")
            try:
                client = genai.Client(api_key=api_key)
                full_prompt = prompt_template_str.format(history=history_str, query=query, results=results_str)

                safety_settings = [
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                ]

                response = await client.aio.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=safety_settings,
                    ),
                )

                if getattr(response, 'text', '') and response.text.strip():
                    filtered_results_str = response.text
                else:
                    finish_reason = 'N/A'
                    try:
                        if getattr(response, 'candidates', None):
                            first = response.candidates[0]
                            finish_reason = getattr(first, 'finish_reason', 'N/A')
                    except Exception:
                        pass
                    print(f"AI response was empty or blocked. Finish reason: {finish_reason}. Fallback to LangChain.")
                    use_langchain_fallback = True
                    
            except Exception as genai_error:
                print(f"Google GenAI SDK error: {genai_error}. Fallback to LangChain.")
                use_langchain_fallback = True
        else:
            use_langchain_fallback = True
            
        # Use LangChain if Google AI failed or not available
        if use_langchain_fallback:
            print("Sử dụng LangChain chain để lọc kết quả.")
            prompt = ChatPromptTemplate.from_template(prompt_template_str)
            chain = prompt | llm | StrOutputParser()
            filtered_results_str = await chain.ainvoke({"query": query, "results": results_str, "history": history_str})

        if not filtered_results_str.strip():
            return []
            
        return [res.strip() for res in filtered_results_str.strip().split("\n\n") if res.strip()]
    except Exception as e:
        print(f"Lỗi khi lọc kết quả bằng AI: {e}")
        return results


JINA_RERANK_MODEL = "jina-reranker-v3"


async def rerank_with_jina(query: str, docs: List[str], top_n: int = 10) -> List[int]:
    """Rerank danh sách văn bản bằng Jina Reranker v3, trả về danh sách index ưu tiên.

    - Nếu thiếu API key hoặc lỗi gọi API, hàm sẽ fallback trả về index gốc (0..top_n-1).
    """
    if not docs:
        return []

    api_key = os.getenv("JINA_API_KEY")
    if not api_key:
        print("[JINA_RERANK] JINA_API_KEY is not set. Skip reranking.")
        return list(range(min(top_n, len(docs))))

    url = "https://api.jina.ai/v1/rerank"
    payload = {
        "model": JINA_RERANK_MODEL,
        "query": query,
        "documents": docs,
        "top_n": min(top_n, len(docs)),
        "return_documents": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    print(f"[JINA_RERANK] HTTP {resp.status}: {text}")
                    return list(range(min(top_n, len(docs))))
                try:
                    data = json.loads(text)
                except Exception:
                    print("[JINA_RERANK] Failed to parse JSON response from Jina.")
                    return list(range(min(top_n, len(docs))))

        results = data.get("results") or data.get("reranked_documents") or []
        indices: List[int] = []
        for item in results:
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < len(docs):
                indices.append(idx)

        if not indices:
            return list(range(min(top_n, len(docs))))
        return indices
    except Exception as e:
        print(f"[JINA_RERANK] Error calling Jina rerank API: {e}")
        return list(range(min(top_n, len(docs))))


def _format_results_for_agent(hits: List[Dict[str, Any]], is_sale_customer: bool = False, show_description: bool = True) -> List[str]:
    """Định dạng danh sách kết quả tìm kiếm thành chuỗi văn bản dễ đọc cho agent."""
    formatted_results = []
    for item in hits:
        context = []
        if 'model' in item: # Product
            context.append(f"Mã sản phẩm: {item.get('ma_san_pham', '')}")
            context.append(f"Sản phẩm: {item.get('model', '')} {item.get('dung_luong', '')} {item.get('mau_sac', '')}".strip())
            if item.get('loai_thiet_bi'):
                context.append(f"  Loại thiết bị: {item.get('loai_thiet_bi')}")
            if item.get('tinh_trang_may'):
                context.append(f"  Tình trạng máy: {item.get('tinh_trang_may')}")
            price = item.get('gia', 0)
            if is_sale_customer:
                price_buon = item.get('gia_buon')
                price_buon_str = (f"{price_buon:,.0f}đ" if price_buon and price_buon > 0 else "Liên hệ")
                context.append(f"  Giá bán buôn: {price_buon_str}")
            inventory = item.get('ton_kho', 0)
            if inventory is not None:
                context.append(f"  Tình trạng: {f'Còn hàng (còn {inventory})' if inventory > 0 else 'Hết hàng'}")
            guarantee = item.get('bao_hanh', '')
            if guarantee:
                context.append(f"  Bảo hành: {guarantee}")
            pin_status = item.get('tinh_trang_pin', '')
            if pin_status:
                context.append(f"  Tình trạng pin: {pin_status}")
            note = item.get('ghi_chu', '')
            if note:
                context.append(f"  Ghi chú: {note}")
            chip_ram = item.get('chip_ram', '')
            if chip_ram:
                context.append(f"  Chip RAM: {chip_ram}")
            camera = item.get('camera', '')
            if camera:
                context.append(f"  Camera: {camera}")
            
        elif 'ten_dich_vu' in item: # Service
            context.append(f"Mã dịch vụ: {item.get('ma_dich_vu', '')}")
            context.append(f"Dịch vụ: {item.get('ten_dich_vu', '')}")
            if item.get('ten_san_pham'):
                context.append(f"  Áp dụng cho sản phẩm: {item.get('ten_san_pham')}")
            if item.get('loai_dich_vu'):
                context.append(f"  Loại dịch vụ: {item.get('loai_dich_vu')}")
            price = item.get('gia', 0)
            if is_sale_customer:
                price_sale = item.get('gia_buon')
                price_sale_str = (f"{price_sale:,.0f}đ" if price_sale and price_sale > 0 else "Liên hệ")
                context.append(f"  Giá bán buôn: {price_sale_str}")
            guarantee = item.get('bao_hanh', '')
            if guarantee:
                context.append(f"  Bảo hành: {guarantee}")
            note = item.get('ghi_chu', '')
            if note:
                context.append(f"  Ghi chú: {note}")

        elif 'accessory_name' in item: # Accessory
            context.append(f"Mã phụ kiện: {item.get('accessory_code', '')}")
            context.append(f"Phụ kiện: {item.get('accessory_name', '')}")
            if item.get('trademark'):
                context.append(f"  Thương hiệu: {item.get('trademark')}")
            if item.get('category'):
                context.append(f"  Danh mục: {item.get('category')}")
            prop = item.get('properties')
            if prop and str(prop).strip() and str(prop).strip() != '0':
                context.append(f"  Thuộc tính: {prop}")
            # Giá phụ kiện: ưu tiên trường gia_ban / gia_si, fallback về lifecare_price / sale_price nếu còn dữ liệu cũ
            price = item.get('gia_ban')
            if price is None:
                price = item.get('lifecare_price', 0)
            if is_sale_customer:
                price_sale = item.get('gia_si')
                if price_sale is None:
                    price_sale = item.get('sale_price')
                price_sale_str = (f"{price_sale:,.0f}đ" if price_sale and price_sale > 0 else "Liên hệ")
                context.append(f"  Giá bán buôn: {price_sale_str}")
            inventory = item.get('inventory')
            if inventory is not None:
                context.append(f"  Tình trạng: {f'Còn hàng (còn {inventory})' if inventory > 0 else 'Hết hàng'}")
            if show_description and item.get('description'):
                context.append(f"  Mô tả: {item.get('description')}")
            if item.get('guarantee'):
                context.append(f"  Bảo hành: {item.get('guarantee')}")
            if item.get('link_product'):
                context.append(f"  Link sản phẩm: {item.get('link_product')}")
            if item.get('avatar_images'):
                context.append(f"  Link ảnh: {item.get('avatar_images')}")
        
        price_str = f"{price:,.0f}đ" if price > 0 else "Liên hệ"
        price_label = "Giá bán lẻ" if is_sale_customer else "Giá"
        context.append(f"  {price_label}: {price_str}")
            
        formatted_results.append("\n".join(context))
    return formatted_results

async def search_products(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    loai_thiet_bi: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    offset: int = 0,
    original_query: Optional[str] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None
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
        try:
            print(
                "[ES-DEBUG] search_products query=",
                json.dumps(
                    {
                        "index": PRODUCTS_INDEX,
                        "routing": sanitized_customer_id,
                        "from": offset,
                        "query": query,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception:
            pass

        response = await es_client.search(
            index=PRODUCTS_INDEX,
            query=query,
            routing=sanitized_customer_id,
            size=10,
            from_=offset
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        print(f"Tìm thấy {len(hits)} sản phẩm phù hợp cho khách hàng '{customer_id}'.")
        is_sale = _get_customer_is_sale(customer_id, thread_id)
        formatted_hits = _format_results_for_agent(hits, is_sale)
        if original_query and llm:
            return await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)
        return formatted_hits
    except Exception as e:
        print(f"Lỗi khi tìm kiếm sản phẩm: {e}")
        return [{"error": f"Lỗi tìm kiếm: {e}"}]

async def search_services(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    ten_dich_vu: Optional[str] = None,
    ten_san_pham: Optional[str] = None,
    loai_dich_vu: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    offset: int = 0,
    original_query: Optional[str] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None
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
    
    if ten_san_pham: query["bool"]["should"].append({"match_phrase": {"ten_san_pham": {"query": ten_san_pham, "boost": 10.0}}})

    if loai_dich_vu:
        query["bool"]["should"].append({"match": {"loai_dich_vu": {"query": loai_dich_vu, "boost": 5.0}}})

    price_range = {}
    if min_gia is not None: price_range["gte"] = min_gia
    if max_gia is not None: price_range["lte"] = max_gia
    if price_range: query["bool"]["filter"].append({"range": {"gia": price_range}})

    try:
        try:
            print(
                "[ES-DEBUG] search_services query=",
                json.dumps(
                    {
                        "index": SERVICES_INDEX,
                        "routing": sanitized_customer_id,
                        "from": offset,
                        "query": query,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception:
            pass

        response = await es_client.search(
            index=SERVICES_INDEX,
            query=query,
            routing=sanitized_customer_id,
            size=10,
            from_=offset
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        if hits:
            print(f"Tìm thấy {len(hits)} dịch vụ phù hợp cho khách hàng '{customer_id}'.")
            is_sale = _get_customer_is_sale(customer_id, thread_id)
            formatted_hits = _format_results_for_agent(hits, is_sale)
            if original_query and llm:
                return await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)
            return formatted_hits

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
                            "fields": ["ten_dich_vu^3", "ten_san_pham^2", "loai_dich_vu^2"],
                            "fuzziness": "AUTO"
                        }
                    },
                    "filter": [
                        {"term": {"customer_id": sanitized_customer_id}}
                    ]
                }
            }
            response = await es_client.search(
                index=SERVICES_INDEX,
                query=fallback_query,
                routing=sanitized_customer_id,
                size=10,
                from_=offset
            )
            hits = [hit['_source'] for hit in response['hits']['hits']]
            print(f"Fallback multi_match: tìm thấy {len(hits)} dịch vụ phù hợp.")
            is_sale = _get_customer_is_sale(customer_id, thread_id)
            formatted_hits = _format_results_for_agent(hits, is_sale)
            if original_query and llm:
                return await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)
            return formatted_hits

        return []
    except Exception as e:
        print(f"Lỗi khi tìm kiếm dịch vụ: {e}")
        return [{"error": f"Lỗi tìm kiếm: {e}"}]

async def search_accessories(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    ten_phu_kien: Optional[str] = None,
    thuong_hieu: Optional[str] = None,
    phan_loai_phu_kien: Optional[str] = None,
    thuoc_tinh_phu_kien: Optional[str] = None,
    cum_dac_trung: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    offset: int = 0,
    original_query: Optional[str] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm phụ kiện trong index 'accessories' chia sẻ, lọc theo customer_id.
    """
    if not es_client:
        return [{"error": "Không thể kết nối đến Elasticsearch."}]

    sanitized_customer_id = sanitize_for_es(customer_id)
    base_bool = {"bool": {"must": [], "should": [], "filter": []}}
    base_bool["bool"]["filter"].append({"term": {"customer_id": sanitized_customer_id}})
    # Chỉ lấy sản phẩm còn hàng
    # base_bool["bool"]["filter"].append({"range": {"inventory": {"gt": 0}}})

    price_range = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia
    if price_range:
        # Lọc theo giá bán đúng trường gia_ban
        base_bool["bool"]["filter"].append({"range": {"gia_ban": price_range}})

    search_terms: List[str] = []
    if ten_phu_kien:
        search_terms.append(str(ten_phu_kien))
    if thuoc_tinh_phu_kien:
        search_terms.append(str(thuoc_tinh_phu_kien))

    if search_terms:
        combined_query = " ".join(search_terms)
        print(f"[ACCESSORY_SEARCH] combined_query: '{combined_query}'")

        base_bool["bool"]["must"].append(
            {
                "match": {
                    "accessory_name": {
                        "query": combined_query
                    }
                }
            }
        )

        base_bool["bool"]["should"].append(
            {
                "multi_match": {
                    "query": combined_query,
                    "fields": [
                        "category",
                        "trademark",
                        "properties",
                    ],
                    "type": "best_fields",
                    "operator": "or",
                }
            }
        )

    if thuong_hieu:
        base_bool["bool"]["should"].append({
            "bool": {
                "should": [
                    {"term": {"trademark.keyword": {"value": thuong_hieu, "boost": 5.0}}},
                    {"match_phrase": {"trademark": {"query": thuong_hieu, "boost": 4.0}}},
                    {"match": {"trademark": thuong_hieu}}
                ]
            }
        })

    if phan_loai_phu_kien:
        base_bool["bool"]["should"].append({
            "bool": {
                "should": [
                    {"term": {"category.keyword": {"value": phan_loai_phu_kien, "boost": 4.0}}},
                    {"match_phrase": {"category": {"query": phan_loai_phu_kien, "boost": 3.0}}},
                    {"match": {"category": phan_loai_phu_kien}}
                ]
            }
        })
    if thuoc_tinh_phu_kien:
        base_bool["bool"]["should"].append({"match_phrase": {"properties": {"query": thuoc_tinh_phu_kien, "boost": 3.0}}})

    search_query = base_bool

    print(f"Sending search to Elasticsearch for accessories: {json.dumps(search_query, indent=2, ensure_ascii=False)}")
    try:
        response = await es_client.search(
            index=ACCESSORIES_INDEX,
            query=search_query,
            routing=sanitized_customer_id,
            size=10,
            from_=offset,
            collapse={"field": "accessory_code.keyword"}
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        # Strip embedding fields to avoid sending large vectors forward
        for _item in hits:
            for _k in list(_item.keys()):
                if _k.endswith("_embedding"):
                    del _item[_k]
        num_hits = len(hits)
        print(f"Tìm thấy {num_hits} phụ kiện phù hợp cho khách hàng '{customer_id}'.")
        
        is_sale = _get_customer_is_sale(customer_id, thread_id)
        # Chỉ hiển thị specifications nếu có <= 5 kết quả
        top_hits = hits[:5]
        rest_hits = hits[5:]
        formatted_hits: List[str] = []
        if top_hits:
            formatted_hits.extend(_format_results_for_agent(top_hits, is_sale, True))
        if rest_hits:
            formatted_hits.extend(_format_results_for_agent(rest_hits, is_sale, False))

        if original_query and llm:
            formatted_hits = await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)

        return formatted_hits

    except Exception as e:
        print(f"Lỗi khi tìm kiếm phụ kiện: {e}")
        return [{"error": f"Lỗi tìm kiếm: {e}"}]

async def search_faqs(
    es_client: AsyncElasticsearch,
    customer_id: str,
    query: str,
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm câu hỏi tương tự trong index FAQ.
    """
    if not es_client:
        return []

    sanitized_customer_id = sanitize_for_es(customer_id)

    try:
        response = await es_client.search(
            index=FAQ_INDEX,
            query={
                "bool": {
                    "must": [
                        {"term": {"customer_id": sanitized_customer_id}},
                        {"match": {"question": query}}
                    ]
                }
            },
            routing=sanitized_customer_id,
            size=1
        )
        return [hit['_source'] for hit in response['hits']['hits']]
    except Exception as e:
        print(f"Lỗi khi tìm kiếm FAQ: {e}")
        return []

async def hybrid_search_products(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None,
) -> List[str]:
    """Hybrid search dành riêng cho sản phẩm dùng chính tính năng hybrid (BM25 + vector) của Elasticsearch.

    - Vector: trường ``model_embedding`` (dense_vector) được tạo từ tên thiết bị ``model`` bằng Google Gemini.
    - Lexical: match trên trường ``model`` và filter theo ``customer_id`` / khoảng giá.
    - Nếu không tạo được embedding, fallback về hàm ``search_products`` cũ (chỉ BM25).
    """
    if not es_client:
        return ["Không thể kết nối đến Elasticsearch."]

    sanitized_customer_id = sanitize_for_es(customer_id)

    # 1) Tạo embedding cho truy vấn
    query_vector: List[float] = []
    try:
        query_vector = await _embed_name_with_google(query)
    except Exception as e:
        print(f"[HYBRID_PRODUCTS] Lỗi tạo embedding cho query '{query}': {e}")
        query_vector = []

    # 2) Nếu không có vector → fallback BM25 như cũ
    if not query_vector:
        try:
            results = await search_products(
                es_client=es_client,
                customer_id=customer_id,
                thread_id=thread_id,
                model=query,
                mau_sac=None,
                dung_luong=None,
                tinh_trang_may=None,
                loai_thiet_bi=None,
                min_gia=min_gia,
                max_gia=max_gia,
                offset=offset,
                original_query=query if llm else None,
                llm=llm,
                chat_history=chat_history,
            )
        except Exception as e:
            print(f"[HYBRID_PRODUCTS] Lỗi fallback search_products: {e}")
            return []

        if not isinstance(results, list):
            return []
        return [r.strip() for r in results if isinstance(r, str) and r.strip()]

    # 3) Hybrid search: knn + lexical query
    price_range: Dict[str, float] = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia

    bool_query: Dict[str, Any] = {
        "filter": [
            {"term": {"customer_id": sanitized_customer_id}},
        ],
        "should": [
            {"match": {"model": query}},
            {"match_phrase": {"model": {"query": query, "boost": 2.0}}},
        ],
        "minimum_should_match": 1,
    }
    if price_range:
        bool_query["filter"].append({"range": {"gia": price_range}})

    try:
        response = await es_client.search(
            index=PRODUCTS_INDEX,
            knn={
                "field": "model_embedding",
                "query_vector": query_vector,
                "k": 10,
                "num_candidates": 50,
            },
            query={"bool": bool_query},
            routing=sanitized_customer_id,
            size=10,
        )

        hits = [hit["_source"] for hit in response["hits"]["hits"]]
        # Strip embedding fields to avoid sending large vectors forward
        for _item in hits:
            for _k in list(_item.keys()):
                if _k.endswith("_embedding"):
                    del _item[_k]

        raw_num_hits = len(hits)
        print(f"[HYBRID_PRODUCTS] Found {raw_num_hits} hits for customer '{customer_id}'.")
        # Lấy trực tiếp top 10 kết quả từ Elasticsearch (không dùng Jina rerank)
        selected_hits = hits[:10]

        num_hits = len(selected_hits)
        print(
            f"[HYBRID_PRODUCTS] Returning top {num_hits} hits from Elasticsearch for customer '{customer_id}'."
        )

        is_sale = _get_customer_is_sale(customer_id, thread_id)
        formatted_hits = _format_results_for_agent(selected_hits, is_sale)

        if llm:
            return await filter_results_with_ai(query, formatted_hits, llm, chat_history)
        return formatted_hits
    except Exception as e:
        print(f"[HYBRID_PRODUCTS] Lỗi hybrid search: {e}")
        return []


async def hybrid_search_services(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None,
) -> List[str]:
    """Hybrid search dành riêng cho dịch vụ sửa chữa dùng BM25 + vector trong Elasticsearch.

    - Vector: trường ``ten_dich_vu_embedding`` được tạo từ ``ten_dich_vu``.
    - Lexical: match trên ``ten_dich_vu`` và filter ``customer_id`` / khoảng giá.
    - Fallback về ``search_services`` nếu không tạo được embedding.
    """
    if not es_client:
        return ["Không thể kết nối đến Elasticsearch."]

    sanitized_customer_id = sanitize_for_es(customer_id)

    query_vector: List[float] = []
    try:
        query_vector = await _embed_name_with_google(query)
    except Exception as e:
        print(f"[HYBRID_SERVICES] Lỗi tạo embedding cho query '{query}': {e}")
        query_vector = []

    if not query_vector:
        try:
            results = await search_services(
                es_client=es_client,
                customer_id=customer_id,
                thread_id=thread_id,
                ten_dich_vu=query,
                ten_san_pham=None,
                loai_dich_vu=None,
                min_gia=min_gia,
                max_gia=max_gia,
                offset=offset,
                original_query=query if llm else None,
                llm=llm,
                chat_history=chat_history,
            )
        except Exception as e:
            print(f"[HYBRID_SERVICES] Lỗi fallback search_services: {e}")
            return []

        if not isinstance(results, list):
            return []
        return [r.strip() for r in results if isinstance(r, str) and r.strip()]

    price_range: Dict[str, float] = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia

    bool_query: Dict[str, Any] = {
        "filter": [
            {"term": {"customer_id": sanitized_customer_id}},
        ],
        "should": [
            {"match": {"ten_dich_vu": query}},
            {"match_phrase": {"ten_dich_vu": {"query": query, "boost": 2.0}}},
        ],
        "minimum_should_match": 1,
    }
    if price_range:
        bool_query["filter"].append({"range": {"gia": price_range}})

    try:
        response = await es_client.search(
            index=SERVICES_INDEX,
            knn={
                "field": "ten_dich_vu_embedding",
                "query_vector": query_vector,
                "k": 10,
                "num_candidates": 50,
            },
            query={"bool": bool_query},
            routing=sanitized_customer_id,
            size=10,
        )

        hits = [hit["_source"] for hit in response["hits"]["hits"]]
        # Strip embedding fields to avoid sending large vectors forward
        for _item in hits:
            for _k in list(_item.keys()):
                if _k.endswith("_embedding"):
                    del _item[_k]

        raw_num_hits = len(hits)
        print(f"[HYBRID_SERVICES] Found {raw_num_hits} hits for customer '{customer_id}'.")
        # Lấy trực tiếp top 10 kết quả từ Elasticsearch (không dùng Jina rerank)
        selected_hits = hits[:10]

        num_hits = len(selected_hits)
        print(
            f"[HYBRID_SERVICES] Returning top {num_hits} hits from Elasticsearch for customer '{customer_id}'."
        )

        is_sale = _get_customer_is_sale(customer_id, thread_id)
        formatted_hits = _format_results_for_agent(selected_hits, is_sale)

        if llm:
            return await filter_results_with_ai(query, formatted_hits, llm, chat_history)
        return formatted_hits
    except Exception as e:
        print(f"[HYBRID_SERVICES] Lỗi hybrid search: {e}")
        return []


async def hybrid_search_accessories(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
    cum_dac_trung: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None,
) -> List[str]:
    """Hybrid search dành riêng cho phụ kiện dùng BM25 + vector trong Elasticsearch.

    - Vector: trường ``accessory_name_embedding`` được tạo từ ``accessory_name``.
    - Lexical: match trên ``accessory_name`` (và ưu tiên cụm đặc trưng nếu có) + filter ``customer_id`` / khoảng giá.
    - Fallback về ``search_accessories`` nếu không tạo được embedding.
    """
    if not es_client:
        return ["Không thể kết nối đến Elasticsearch."]

    sanitized_customer_id = sanitize_for_es(customer_id)

    query_vector: List[float] = []
    try:
        query_vector = await _embed_name_with_google(query)
    except Exception as e:
        print(f"[HYBRID_ACCESSORIES] Lỗi tạo embedding cho query '{query}': {e}")
        query_vector = []

    if not query_vector:
        try:
            results = await search_accessories(
                es_client=es_client,
                customer_id=customer_id,
                thread_id=thread_id,
                ten_phu_kien=query,
                thuong_hieu=None,
                phan_loai_phu_kien=None,
                thuoc_tinh_phu_kien=None,
                cum_dac_trung=cum_dac_trung,
                min_gia=min_gia,
                max_gia=max_gia,
                offset=offset,
                original_query=query if llm else None,
                llm=llm,
                chat_history=chat_history,
            )
        except Exception as e:
            print(f"[HYBRID_ACCESSORIES] Lỗi fallback search_accessories: {e}")
            return []

        if not isinstance(results, list):
            return []
        return [r.strip() for r in results if isinstance(r, str) and r.strip()]

    price_range: Dict[str, float] = {}
    if min_gia is not None:
        price_range["gte"] = min_gia
    if max_gia is not None:
        price_range["lte"] = max_gia

    # Lexical query: match accessory_name + filter customer_id / khoảng giá
    bool_query: Dict[str, Any] = {
        "filter": [
            {"term": {"customer_id": sanitized_customer_id}},
        ],
        "should": [
            {"match": {"accessory_name": query}},
            {"match_phrase": {"accessory_name": {"query": query, "boost": 2.0}}},
        ],
        "minimum_should_match": 1,
    }
    if price_range:
        # Lọc theo giá bán đúng trường gia_ban
        bool_query["filter"].append({"range": {"gia_ban": price_range}})

    # Vector: dùng đúng field accessory_name_embedding trong ES
    knn_body: Dict[str, Any] = {
        "field": "accessory_name_embedding",
        "query_vector": query_vector,
        "k": 10,
        "num_candidates": 50,
    }

    try:
        # Log ES query nhưng bỏ query_vector để tránh log quá dài
        knn_log = dict(knn_body)
        if "query_vector" in knn_log:
            knn_log["query_vector"] = f"<vector_len={len(knn_body['query_vector'])}>"
        # print(
        #     "[HYBRID_ACCESSORIES] ES query:",
        #     json.dumps(
        #         {
        #             "knn": knn_log,
        #             "query": {"bool": bool_query},
        #             "routing": sanitized_customer_id,
        #             "size": 50,
        #         },
        #         ensure_ascii=False,
        #     ),
        # )

        response = await es_client.search(
            index=ACCESSORIES_INDEX,
            knn=knn_body,
            query={"bool": bool_query},
            routing=sanitized_customer_id,
            size=10,
        )

        hits = [hit["_source"] for hit in response["hits"]["hits"]]
        # Strip embedding fields để không gửi vector to cho LLM
        for _item in hits:
            for _k in list(_item.keys()):
                if _k.endswith("_embedding"):
                    del _item[_k]

        raw_num_hits = len(hits)
        print(f"[HYBRID_ACCESSORIES] Found {raw_num_hits} hits for customer '{customer_id}'.")
        try:
            accessory_names = [str(_item.get("accessory_name", "")) for _item in hits]
            print(
                "[HYBRID_ACCESSORIES] Accessory names:",
                json.dumps(accessory_names, ensure_ascii=False),
            )
            # Log chi tiết tất cả các trường sau khi tìm từ ES (loại bỏ embedding và các trường giá cũ)
            print("[HYBRID_ACCESSORIES] === RAW ES HITS (ALL FIELDS) ===")
            for idx, _item in enumerate(hits):
                _item_log = {
                    k: v
                    for k, v in _item.items()
                    if not k.endswith("_embedding") and k not in ("specifications", "description", "lifecare_price", "sale_price")
                }
            
                # print(f"[HYBRID_ACCESSORIES] Hit #{idx}: {json.dumps(_item_log, ensure_ascii=False, default=str)}")
            print("[HYBRID_ACCESSORIES] === END RAW ES HITS ===")
        except Exception as log_err:
            print(f"[HYBRID_ACCESSORIES] Lỗi log raw hits: {log_err}")

        # Lấy trực tiếp top 10 kết quả từ Elasticsearch (không dùng Jina rerank)
        selected_hits = hits[:10]

        num_hits = len(selected_hits)
        print(
            f"[HYBRID_ACCESSORIES] Returning top {num_hits} hits from Elasticsearch for customer '{customer_id}'."
        )
        try:
            selected_names = [str(_item.get("accessory_name", "")) for _item in selected_hits]
            print(
                "[HYBRID_ACCESSORIES] Selected accessory names:",
                json.dumps(selected_names, ensure_ascii=False),
            )
        except Exception as log_err:
            print(f"[HYBRID_ACCESSORIES] Lỗi log selected hits: {log_err}")

        is_sale = _get_customer_is_sale(customer_id, thread_id)
        # Chỉ hiển thị description nếu có <= 5 kết quả sau khi chọn top 10
        top_hits = selected_hits[:5]
        rest_hits = selected_hits[5:]
        formatted_hits: List[str] = []
        if top_hits:
            formatted_hits.extend(_format_results_for_agent(top_hits, is_sale, True))
        if rest_hits:
            formatted_hits.extend(_format_results_for_agent(rest_hits, is_sale, False))

        if llm:
            return await filter_results_with_ai(query, formatted_hits, llm, chat_history)
        return formatted_hits
    except Exception as e:
        print(f"[HYBRID_ACCESSORIES] Lỗi hybrid search: {e}")
        return []

async def hybrid_search(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
    include_products: bool = True,
    include_services: bool = True,
    include_accessories: bool = True,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    llm: Optional[Any] = None,
    chat_history: Optional[List[str]] = None
) -> List[str]:
    """Tìm kiếm hybrid trên nhiều loại dữ liệu (sản phẩm, dịch vụ, phụ kiện) trong Elasticsearch.

    Hàm này sẽ:
    - Gọi lại các hàm search_products / search_services / search_accessories hiện có để lấy kết quả dạng text đã format sẵn cho agent.
    - Gom tất cả kết quả lại thành một danh sách chung.
    - Nếu truyền vào LLM, dùng filter_results_with_ai để lọc/xếp hạng lại dựa trên câu hỏi gốc và lịch sử chat.
    """
    if not es_client:
        return ["Không thể kết nối đến Elasticsearch."]

    all_results: List[str] = []

    if include_products:
        try:
            product_results = await search_products(
                es_client=es_client,
                customer_id=customer_id,
                thread_id=thread_id,
                model=None,
                mau_sac=None,
                dung_luong=None,
                tinh_trang_may=None,
                loai_thiet_bi=None,
                min_gia=min_gia,
                max_gia=max_gia,
                offset=offset,
                original_query=None,
                llm=None,
                chat_history=None,
            )
            if isinstance(product_results, list):
                for r in product_results:
                    if isinstance(r, str) and r.strip():
                        all_results.append(f"[SẢN PHẨM]\n{r}")
        except Exception as e:
            print(f"Lỗi khi hybrid search sản phẩm: {e}")

    if include_services:
        try:
            service_results = await search_services(
                es_client=es_client,
                customer_id=customer_id,
                thread_id=thread_id,
                ten_dich_vu=None,
                ten_san_pham=None,
                loai_dich_vu=None,
                min_gia=min_gia,
                max_gia=max_gia,
                offset=offset,
                original_query=None,
                llm=None,
                chat_history=None,
            )
            if isinstance(service_results, list):
                for r in service_results:
                    if isinstance(r, str) and r.strip():
                        all_results.append(f"[DỊCH VỤ]\n{r}")
        except Exception as e:
            print(f"Lỗi khi hybrid search dịch vụ: {e}")

    if include_accessories:
        try:
            accessory_results = await search_accessories(
                es_client=es_client,
                customer_id=customer_id,
                thread_id=thread_id,
                ten_phu_kien=None,
                thuong_hieu=None,
                phan_loai_phu_kien=None,
                thuoc_tinh_phu_kien=None,
                cum_dac_trung=None,
                min_gia=min_gia,
                max_gia=max_gia,
                offset=offset,
                original_query=None,
                llm=None,
                chat_history=None,
            )
            if isinstance(accessory_results, list):
                for r in accessory_results:
                    if isinstance(r, str) and r.strip():
                        all_results.append(f"[PHỤ KIỆN]\n{r}")
        except Exception as e:
            print(f"Lỗi khi hybrid search phụ kiện: {e}")

    if not all_results:
        return []

    if llm:
        return await filter_results_with_ai(query, all_results, llm, chat_history)

    return all_results

if __name__ == '__main__':
    import asyncio

    async def main():
        es_client_mock = AsyncElasticsearch()
        results = await search_products(es_client_mock, customer_id="customer123", thread_id="thread123", model="iPhone 15 Pro Max", mau_sac="Titan Tự nhiên")
        if results:
            for product in results:
                print(product)

    asyncio.run(main())
