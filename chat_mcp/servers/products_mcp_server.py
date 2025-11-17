"""MCP server cho domain sản phẩm (products).

Skeleton này mô tả cách expose logic ``search_products`` hiện tại qua MCP.
Sau này server này sẽ được chạy như một process riêng, backend sẽ gọi qua langchain-mcp-adapters.
"""

from typing import Any, Dict, Optional, List
import json

from elasticsearch import AsyncElasticsearch
from sqlalchemy.orm import Session
from config.settings import ELASTIC_HOST
from database.database import CustomerIsSale, SessionLocal
from service.prompts.prompt_service import load_instructions
from service.data.data_loader_elastic_search import PRODUCTS_INDEX
from service.utils.helpers import sanitize_for_es
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP


mcp = FastMCP(name="products-mcp")


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
     chat_history: Optional[List[str]] = None,
 ) -> List[Dict[str, Any]]:
     """Tìm kiếm sản phẩm trong index 'products' chia sẻ, lọc theo customer_id."""
     if not es_client:
         return [{"error": "Không thể kết nối đến Elasticsearch."}]

     sanitized_customer_id = sanitize_for_es(customer_id)
     query: Dict[str, Any] = {"bool": {"must": [], "should": [], "filter": []}}

     query["bool"]["filter"].append({"term": {"customer_id": sanitized_customer_id}})

     if model:
         query["bool"]["must"].append(
             {
                 "bool": {
                     "should": [
                         {"term": {"model.keyword": {"value": model, "boost": 3.0}}},
                         {"match_phrase": {"model": {"query": model, "boost": 2.0}}},
                         {"match": {"model": model}},
                     ]
                 }
             }
         )

     if mau_sac:
         query["bool"]["must"].append({"match": {"mau_sac": mau_sac}})
     if loai_thiet_bi:
         query["bool"]["should"].append({"match": {"loai_thiet_bi": loai_thiet_bi}})
     if dung_luong:
         query["bool"]["must"].append({"match": {"dung_luong": dung_luong}})
     if tinh_trang_may:
         query["bool"]["should"].append({"match": {"tinh_trang_may": tinh_trang_may}})

     price_range: Dict[str, Any] = {}
     if min_gia is not None:
         price_range["gte"] = min_gia
     if max_gia is not None:
         price_range["lte"] = max_gia
     if price_range:
         query["bool"]["filter"].append({"range": {"gia": price_range}})

     try:
         response = await es_client.search(
             index=PRODUCTS_INDEX,
             query=query,
             routing=sanitized_customer_id,
             size=10,
             from_=offset,
         )
         hits = [hit["_source"] for hit in response["hits"]["hits"]]
         print(f"Tìm thấy {len(hits)} sản phẩm phù hợp cho khách hàng '{customer_id}'.")
         is_sale = _get_customer_is_sale(customer_id, thread_id)
         formatted_hits = _format_results_for_agent(hits, is_sale)
         if original_query and llm:
             return await filter_results_with_ai(original_query, formatted_hits, llm, chat_history)
         return formatted_hits
     except Exception as e:
         print(f"Lỗi khi tìm kiếm sản phẩm: {e}")
         return [{"error": f"Lỗi tìm kiếm: {e}"}]


_es_client: Optional[AsyncElasticsearch] = None


async def _get_es_client() -> AsyncElasticsearch:
    """Khởi tạo/lấy lại client Elasticsearch dùng chung cho MCP server products.

    Đơn giản hoá: giữ một AsyncElasticsearch toàn cục trong process MCP.
    """

    global _es_client
    if _es_client is None:
        _es_client = AsyncElasticsearch(hosts=[ELASTIC_HOST])
    return _es_client


@mcp.tool()
async def products_search(
    customer_id: str,
    thread_id: str,
    query: str,
    offset: int = 0,
) -> Dict[str, Any]:
    """Tìm kiếm sản phẩm cho một customer.

    Tham số:
    - customer_id: mã khách hàng (tenant).
    - thread_id: mã phiên chat, dùng để phân biệt khách lẻ/buôn như logic cũ.
    - query: câu hỏi gốc của người dùng, map sang ``original_query``.
    - offset: phân trang (bỏ qua N kết quả đầu).

    Triển khai:
    - Gọi lại hàm ``search_products`` trong ``service.retrieve.search_service``.
    - Tạm thời map query → original_query, chưa bẻ nhỏ thành model/màu/dung lượng.
    """

    es = await _get_es_client()
    try:
        results = await search_products(
            es_client=es,
            customer_id=customer_id,
            thread_id=thread_id,
            model=None,
            mau_sac=None,
            dung_luong=None,
            tinh_trang_may=None,
            loai_thiet_bi=None,
            min_gia=None,
            max_gia=None,
            offset=offset,
            original_query=query,
            llm=None,
            chat_history=None,
        )
        return {"results": results}
    except Exception as e:
        # MCP tool nên luôn trả về JSON, nên bọc lỗi thành field error.
        return {"error": str(e)}


if __name__ == "__main__":
    # Khi chạy trực tiếp file này, khởi động MCP server products-mcp.
    mcp.run()
