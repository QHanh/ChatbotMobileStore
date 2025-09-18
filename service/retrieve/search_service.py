from elasticsearch import AsyncElasticsearch
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from database.database import CustomerIsSale, SessionLocal
from service.data.data_loader_elastic_search import PRODUCTS_INDEX, SERVICES_INDEX, ACCESSORIES_INDEX, FAQ_INDEX
from service.utils.helpers import sanitize_for_es
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai.chat_models import ChatGoogleGenerativeAI
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

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
    prompt_template_str = """
            Bạn là một trợ lý AI có nhiệm vụ lọc kết quả tìm kiếm một cách nghiêm ngặt. Dựa trên LỊCH SỬ TRÒ CHUYỆN và CÂU HỎI HIỆN TẠI của người dùng, hãy lọc và chỉ giữ lại những kết quả tìm kiếm THỰC SỰ liên quan.

            **QUY TRÌNH LỌC:**
            1.  **Phân tích câu hỏi:** Xác định các **từ khóa chính** trong câu hỏi của người dùng, đặc biệt chú ý đến **thương hiệu** (ví dụ: KAISI, Apple), **tên model cụ thể** (ví dụ: TX-50S), và các **thuộc tính quan trọng** (ví dụ: "2 mắt", "màu xanh").
            2.  **Đối chiếu nghiêm ngặt:** So sánh từng kết quả tìm kiếm với các từ khóa chính này. Một kết quả CHỈ được coi là phù hợp nếu nó chứa **TẤT CẢ** các từ khóa chính mà người dùng đã nêu. Ví dụ, nếu người dùng hỏi "kính hiển vi KAISI 2 mắt", kết quả bắt buộc phải chứa cả "KAISI" và "2 mắt".
            
            **QUY TẮC XUẤT KẾT QUẢ:**
            -   Chỉ trả về các kết quả phù hợp sau khi đã đối chiếu nghiêm ngặt.
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

    try:
        filtered_results_str = ""
        use_langchain_fallback = False
        
        if isinstance(llm, ChatGoogleGenerativeAI) and llm.google_api_key:
            print("Sử dụng Google AI SDK gốc để lọc kết quả.")
            try:
                genai.configure(api_key=llm.google_api_key.get_secret_value())
                model = genai.GenerativeModel(model_name="gemini-2.0-flash")
                full_prompt = prompt_template_str.format(history=history_str, query=query, results=results_str)
                
                safety_settings = {
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }

                response = await model.generate_content_async(full_prompt, safety_settings=safety_settings)
                
                if response.parts and response.text.strip():
                    filtered_results_str = response.text
                else:
                    finish_reason = 'N/A'
                    if response.candidates and len(response.candidates) > 0:
                        finish_reason = response.candidates[0].finish_reason.name
                    print(f"AI response was empty or blocked. Finish reason: {finish_reason}. Fallback to LangChain.")
                    use_langchain_fallback = True
                    
            except Exception as genai_error:
                print(f"Google AI SDK error: {genai_error}. Fallback to LangChain.")
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

def _format_results_for_agent(hits: List[Dict[str, Any]], is_sale_customer: bool = False) -> List[str]:
    """Định dạng danh sách kết quả tìm kiếm thành chuỗi văn bản dễ đọc cho agent."""
    formatted_results = []
    for item in hits:
        context = []
        if 'model' in item: # Product
            context.append(f"Mã sản phẩm: {item.get('ma_san_pham', '')}")
            context.append(f"Sản phẩm: {item.get('model', '')} {item.get('dung_luong', '')} {item.get('mau_sac', '')}".strip())
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
            prop = item.get('properties')
            if prop and str(prop).strip() and str(prop).strip() != '0':
                context.append(f"  Thuộc tính: {prop}")
            price = item.get('lifecare_price', 0)
            if is_sale_customer:
                price_sale = item.get('sale_price')
                price_sale_str = (f"{price_sale:,.0f}đ" if price_sale and price_sale > 0 else "Liên hệ")
                context.append(f"  Giá bán buôn: {price_sale_str}")
            inventory = item.get('inventory')
            if inventory is not None:
                context.append(f"  Tình trạng: {f'Còn hàng (còn {inventory})' if inventory > 0 else 'Hết hàng'}")
            # if item.get('specifications'):
            #     context.append(f"  Mô tả: {item.get('specifications')}")
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
    phan_loai_phu_kien: Optional[str] = None,
    thuoc_tinh_phu_kien: Optional[str] = None,
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
            size=10,
            from_=offset
        )
        hits = [hit['_source'] for hit in response['hits']['hits']]
        print(f"Tìm thấy {len(hits)} phụ kiện phù hợp cho khách hàng '{customer_id}'.")
        is_sale = _get_customer_is_sale(customer_id, thread_id)
        formatted_hits = _format_results_for_agent(hits, is_sale)
        if original_query and llm:
            return await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)
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

if __name__ == '__main__':
    import asyncio

    async def main():
        es_client_mock = AsyncElasticsearch()
        results = await search_products(es_client_mock, customer_id="customer123", thread_id="thread123", model="iPhone 15 Pro Max", mau_sac="Titan Tự nhiên")
        if results:
            for product in results:
                print(product)

    asyncio.run(main())
