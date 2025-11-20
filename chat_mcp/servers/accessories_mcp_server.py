"""MCP server cho domain phụ kiện (accessories).

Wrap logic ``search_accessories`` hiện tại qua MCP.
"""

from typing import Any, Dict, Optional, List
import json

from elasticsearch import AsyncElasticsearch
from sqlalchemy.orm import Session
from config.settings import ELASTIC_HOST
from database.database import CustomerIsSale, SessionLocal
from service.prompts.prompt_service import load_instructions
from service.data.data_loader_elastic_search import ACCESSORIES_INDEX
from service.utils.helpers import sanitize_for_es
from service.retrieve.search_service import search_accessories as core_search_accessories
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP


mcp = FastMCP(name="accessories-mcp")


def _get_customer_is_sale(customer_id: str, thread_id: str) -> bool:
    """Kiểm tra xem thread có phải là của khách hàng mua buôn hay không."""
    if not thread_id:
        return False
    db: Session = SessionLocal()
    try:
        sale_status = db.query(CustomerIsSale).filter(
            CustomerIsSale.customer_id == customer_id,
            CustomerIsSale.thread_id == thread_id,
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
     chat_history: Optional[List[str]] = None,
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
             """,
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
                     types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                     types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                     types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                     types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                 ]

                 response = await client.aio.models.generate_content(
                     model="gemini-2.5-flash",
                     contents=full_prompt,
                     config=types.GenerateContentConfig(
                         safety_settings=safety_settings,
                     ),
                 )

                 if getattr(response, "text", "") and response.text.strip():
                     filtered_results_str = response.text
                 else:
                     finish_reason = "N/A"
                     try:
                         if getattr(response, "candidates", None):
                             first = response.candidates[0]
                             finish_reason = getattr(first, "finish_reason", "N/A")
                     except Exception:
                         pass
                     print(
                         f"AI response was empty or blocked. Finish reason: {finish_reason}. Fallback to LangChain."
                     )
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
             filtered_results_str = await chain.ainvoke(
                 {"query": query, "results": results_str, "history": history_str}
             )

         if not filtered_results_str.strip():
             return []

         return [res.strip() for res in filtered_results_str.strip().split("\n\n") if res.strip()]
     except Exception as e:
         print(f"Lỗi khi lọc kết quả bằng AI: {e}")
         return results


def _format_results_for_agent(
     hits: List[Dict[str, Any]],
     is_sale_customer: bool = False,
     show_specifications: bool = True,
 ) -> List[str]:
     """Định dạng danh sách kết quả tìm kiếm thành chuỗi văn bản dễ đọc cho agent."""
     formatted_results = []
     for item in hits:
         context = []
         if "model" in item:  # Product
             context.append(f"Mã sản phẩm: {item.get('ma_san_pham', '')}")
             context.append(
                 f"Sản phẩm: {item.get('model', '')} {item.get('dung_luong', '')} {item.get('mau_sac', '')}".strip()
             )
             if item.get("loai_thiet_bi"):
                 context.append(f"  Loại thiết bị: {item.get('loai_thiet_bi')}")
             if item.get("tinh_trang_may"):
                 context.append(f"  Tình trạng máy: {item.get('tinh_trang_may')}")
             price = item.get("gia", 0)
             if is_sale_customer:
                 price_buon = item.get("gia_buon")
                 price_buon_str = f"{price_buon:,.0f}đ" if price_buon and price_buon > 0 else "Liên hệ"
                 context.append(f"  Giá bán buôn: {price_buon_str}")
             inventory = item.get("ton_kho", 0)
             if inventory is not None:
                 context.append(
                     f"  Tình trạng: {'Còn hàng (còn ' + str(inventory) + ')' if inventory > 0 else 'Hết hàng'}"
                 )
             guarantee = item.get("bao_hanh", "")
             if guarantee:
                 context.append(f"  Bảo hành: {guarantee}")
             pin_status = item.get("tinh_trang_pin", "")
             if pin_status:
                 context.append(f"  Tình trạng pin: {pin_status}")
             note = item.get("ghi_chu", "")
             if note:
                 context.append(f"  Ghi chú: {note}")
             chip_ram = item.get("chip_ram", "")
             if chip_ram:
                 context.append(f"  Chip RAM: {chip_ram}")
             camera = item.get("camera", "")
             if camera:
                 context.append(f"  Camera: {camera}")

         elif "ten_dich_vu" in item:  # Service
             context.append(f"Mã dịch vụ: {item.get('ma_dich_vu', '')}")
             context.append(f"Dịch vụ: {item.get('ten_dich_vu', '')}")
             if item.get("ten_san_pham"):
                 context.append(f"  Áp dụng cho sản phẩm: {item.get('ten_san_pham')}")
             if item.get("loai_dich_vu"):
                 context.append(f"  Loại dịch vụ: {item.get('loai_dich_vu')}")
             price = item.get("gia", 0)
             if is_sale_customer:
                 price_sale = item.get("gia_buon")
                 price_sale_str = f"{price_sale:,.0f}đ" if price_sale and price_sale > 0 else "Liên hệ"
                 context.append(f"  Giá bán buôn: {price_sale_str}")
             guarantee = item.get("bao_hanh", "")
             if guarantee:
                 context.append(f"  Bảo hành: {guarantee}")
             note = item.get("ghi_chu", "")
             if note:
                 context.append(f"  Ghi chú: {note}")

         elif "accessory_name" in item:  # Accessory
             context.append(f"Mã phụ kiện: {item.get('accessory_code', '')}")
             context.append(f"Phụ kiện: {item.get('accessory_name', '')}")
             if item.get("trademark"):
                 context.append(f"  Thương hiệu: {item.get('trademark')}")
             if item.get("category"):
                 context.append(f"  Danh mục: {item.get('category')}")
             prop = item.get("properties")
             if prop and str(prop).strip() and str(prop).strip() != "0":
                 context.append(f"  Thuộc tính: {prop}")
             price = item.get("lifecare_price", 0)
             if is_sale_customer:
                 price_sale = item.get("sale_price")
                 price_sale_str = f"{price_sale:,.0f}đ" if price_sale and price_sale > 0 else "Liên hệ"
                 context.append(f"  Giá bán buôn: {price_sale_str}")
             inventory = item.get("inventory")
             if inventory is not None:
                 context.append(
                     f"  Tình trạng: {'Còn hàng (còn ' + str(inventory) + ')' if inventory > 0 else 'Hết hàng'}"
                 )
             if show_specifications and item.get("specifications"):
                 context.append(f"  Mô tả: {item.get('specifications')}")
             if item.get("guarantee"):
                 context.append(f"  Bảo hành: {item.get('guarantee')}")
             if item.get("link_product"):
                 context.append(f"  Link sản phẩm: {item.get('link_product')}")
             if item.get("avatar_images"):
                 context.append(f"  Link ảnh: {item.get('avatar_images')}")

         price_str = f"{price:,.0f}đ" if price > 0 else "Liên hệ"
         price_label = "Giá bán lẻ" if is_sale_customer else "Giá"
         context.append(f"  {price_label}: {price_str}")

         formatted_results.append("\n".join(context))
     return formatted_results


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
     chat_history: Optional[List[str]] = None,
 ) -> List[Dict[str, Any]]:
     """
     Tìm kiếm phụ kiện trong index 'accessories' chia sẻ, lọc theo customer_id.
     """
     if not es_client:
         return [{"error": "Không thể kết nối đến Elasticsearch."}]

     sanitized_customer_id = sanitize_for_es(customer_id)
     base_bool: Dict[str, Any] = {"bool": {"must": [], "should": [], "filter": []}}
     base_bool["bool"]["filter"].append({"term": {"customer_id": sanitized_customer_id}})
     # Chỉ lấy sản phẩm còn hàng
     # base_bool["bool"]["filter"].append({"range": {"inventory": {"gt": 0}}})

     price_range: Dict[str, Any] = {}
     if min_gia is not None:
         price_range["gte"] = min_gia
     if max_gia is not None:
         price_range["lte"] = max_gia
     if price_range:
         base_bool["bool"]["filter"].append({"range": {"lifecare_price": price_range}})

     search_terms: List[str] = []
     if ten_phu_kien:
         search_terms.append(str(ten_phu_kien))
     if thuoc_tinh_phu_kien:
         search_terms.append(str(thuoc_tinh_phu_kien))

     if search_terms:
         combined_query = " ".join(search_terms)

         if cum_dac_trung and str(cum_dac_trung).strip():
             # Nếu LLM cung cấp cụm đặc trưng: dùng MUST với match_phrase chính xác
             print(f"[SEARCH] Dùng cum_dac_trung '{cum_dac_trung}' với MUST clause")
             base_bool["bool"]["must"].append(
                 {
                     "match_phrase": {
                         "accessory_name": {
                             "query": str(cum_dac_trung).strip(),
                             "boost": 20.0,
                         }
                     }
                 }
             )
         else:
             # Nếu KHÔNG có cụm đặc trưng: dùng logic cũ với minimum_should_match 70%
             print("[SEARCH] Không phát hiện cụm đặc trưng, dùng minimum_should_match 70%")
             base_bool["bool"]["must"].append(
                 {
                     "match": {
                         "accessory_name": {
                             "query": combined_query,
                             "minimum_should_match": "70%",
                         }
                     }
                 }
             )

             # Ưu tiên cao hơn cho match chính xác
             base_bool["bool"]["should"].extend(
                 [
                     {
                         "match_phrase": {
                             "accessory_name": {
                                 "query": combined_query,
                                 "boost": 10.0,
                             }
                         }
                     },
                     # Tìm kiếm trong các trường khác để tăng điểm
                     {
                         "multi_match": {
                             "query": combined_query,
                             "fields": [
                                 "category^3",
                                 "trademark^2",
                                 "properties^1",
                             ],
                             "type": "best_fields",
                             "operator": "or",
                         }
                     },
                 ]
             )

     if thuong_hieu:
         base_bool["bool"]["should"].append(
             {
                 "bool": {
                     "should": [
                         {"term": {"trademark.keyword": {"value": thuong_hieu, "boost": 5.0}}},
                         {"match_phrase": {"trademark": {"query": thuong_hieu, "boost": 4.0}}},
                         {"match": {"trademark": thuong_hieu}},
                     ]
                 }
             }
         )

     if phan_loai_phu_kien:
         base_bool["bool"]["should"].append(
             {
                 "bool": {
                     "should": [
                         {
                             "term": {
                                 "category.keyword": {
                                     "value": phan_loai_phu_kien,
                                     "boost": 4.0,
                                 }
                             }
                         },
                         {"match_phrase": {"category": {"query": phan_loai_phu_kien, "boost": 3.0}}},
                         {"match": {"category": phan_loai_phu_kien}},
                     ]
                 }
             }
         )
     if thuoc_tinh_phu_kien:
         base_bool["bool"]["should"].append(
             {"match_phrase": {"properties": {"query": thuoc_tinh_phu_kien, "boost": 3.0}}}
         )

     search_query = base_bool

     print(
         f"Sending search to Elasticsearch for accessories: {json.dumps(search_query, indent=2, ensure_ascii=False)}"
     )
     try:
         response = await es_client.search(
             index=ACCESSORIES_INDEX,
             query=search_query,
             routing=sanitized_customer_id,
             size=10,
             from_=offset,
             collapse={"field": "accessory_code.keyword"},
         )
         hits = [hit["_source"] for hit in response["hits"]["hits"]]
         num_hits = len(hits)
         print(f"Tìm thấy {num_hits} phụ kiện phù hợp cho khách hàng '{customer_id}'.")

         is_sale = _get_customer_is_sale(customer_id, thread_id)
         # Chỉ hiển thị specifications nếu có <= 5 kết quả
         show_specs = num_hits <= 5
         formatted_hits = _format_results_for_agent(hits, is_sale, show_specs)

         if original_query and llm:
             formatted_hits = await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)

         try:
             print(
                 f"[ACCESSORIES_MCP] search_accessories result count={len(formatted_hits)} "
                 f"for customer_id='{customer_id}', thread_id='{thread_id}', original_query={original_query!r}"
             )
         except Exception:
             pass

         return formatted_hits

     except Exception as e:
         print(f"Lỗi khi tìm kiếm phụ kiện: {e}")
         return [{"error": f"Lỗi tìm kiếm: {e}"}]


_es_client: Optional[AsyncElasticsearch] = None

async def _get_es_client() -> AsyncElasticsearch:
    """Khởi tạo/lấy lại client Elasticsearch dùng chung cho MCP server accessories."""

    global _es_client
    if _es_client is None:
        _es_client = AsyncElasticsearch(hosts=[ELASTIC_HOST])
    return _es_client


from chat_mcp.core.constants import TOOL_ACCESSORIES_SEARCH

@mcp.tool(name=TOOL_ACCESSORIES_SEARCH)
async def accessories_search(
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
    cum_dac_trung: Optional[str] = None,
) -> Dict[str, Any]:
    """Tìm kiếm phụ kiện cho một customer.

    - query: tạm map sang ``ten_phu_kien`` + ``original_query``.
    - cum_dac_trung: truyền thẳng xuống ``search_accessories`` để giữ đúng rule cụm đặc trưng.
    """

    es = await _get_es_client()
    try:
        results = await core_search_accessories(
            es_client=es,
            customer_id=customer_id,
            thread_id=thread_id,
            ten_phu_kien=query,
            thuong_hieu=None,
            phan_loai_phu_kien=None,
            thuoc_tinh_phu_kien=None,
            cum_dac_trung=cum_dac_trung,
            min_gia=None,
            max_gia=None,
            offset=offset,
            original_query=query,
            llm=None,
            chat_history=None,
        )

        try:
            print(
                f"[ACCESSORIES_MCP] accessories_search called with customer_id={customer_id!r}, "
                f"thread_id={thread_id!r}, query={query!r}, offset={offset}, cum_dac_trung={cum_dac_trung!r}, "
                f"results_len={len(results) if isinstance(results, list) else 'N/A'}"
            )
        except Exception:
            pass

        return {"results": results}
    except Exception as e:
        try:
            print(
                f"[ACCESSORIES_MCP] accessories_search error for customer_id={customer_id!r}, "
                f"thread_id={thread_id!r}, query={query!r}: {e}"
            )
        except Exception:
            pass
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
