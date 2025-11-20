"""Các TypedDict mô tả state hội thoại đa kênh/multi-tenant.

State này được thiết kế để dùng chung cho nhiều workflow LangGraph, ví dụ:
- router intent
- product/service/faq/order flow
- draft & send reply

Nguyên tắc:
- State chỉ chứa dữ liệu thô (raw), không chứa prompt.
- Tách nhỏ thành nhiều TypedDict con (Intent, ProductResult, ...) để tái sử dụng.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class Intent(TypedDict, total=False):
    """Thông tin intent đã được LLM hoặc rule phân loại.

    - name: tên intent chính, dùng để route sang flow tương ứng.
    - confidence: độ tự tin (0-1).
    - sub_intent: intent phụ/chi tiết hơn nếu có.
    - reason: giải thích ngắn vì sao model chọn intent này.
    """

    name: Literal["product_search", "service_search", "order_issue", "faq", "other"]
    confidence: float
    sub_intent: str
    reason: str


class ProductResult(TypedDict, total=False):
    """Kết quả tìm kiếm sản phẩm (raw) cho một lượt hỏi.

    - items: danh sách item raw từ ES/DB/MCP.
    - total: tổng số item tìm thấy.
    - selected_item_id: id sản phẩm đã chọn (nếu người dùng đã chốt).
    """

    items: list[dict]
    total: int
    selected_item_id: str | None


class ServiceResult(TypedDict, total=False):
    """Kết quả tìm kiếm dịch vụ (sửa chữa/bảo hành...)."""

    items: list[dict]
    total: int
    selected_service_id: str | None


class OrderResult(TypedDict, total=False):
    """Thông tin liên quan tới đơn hàng của khách."""

    orders: list[dict]
    draft_order: dict | None


class FaqResult(TypedDict, total=False):
    """Kết quả tra cứu FAQ/knowledge base."""

    answer: str | None
    source_docs: list[dict]


class ErrorInfo(TypedDict, total=False):
    """Thông tin lỗi dùng chung cho các node/tool.

    Có thể log lại code/message/detail để debug.
    """

    code: str
    message: str
    detail: Any


class ChatState(TypedDict, total=False):
    """State hội thoại chuẩn cho hệ thống multi-tenant đa kênh.

    State này phù hợp để dùng với ``StateGraph(ChatState)``.
    Các node sẽ chỉ đọc/ghi một phần nhỏ của state (đúng trách nhiệm của node).
    """

    # ---- Multi-tenant & context ----
    tenant_id: str  # Ví dụ: "shop_xxx"
    channel: Literal["zalo", "facebook", "instagram", "tiktok", "web"]
    session_id: str  # thread / conversation id
    customer_id: str | None
    customer_profile: dict | None  # raw từ CRM

    # ---- Raw message ----
    user_message: str
    attachments: list[dict] | None
    timestamp: str  # ISO string

    # ---- LLM & intent ----
    intent: Intent | None
    messages: list[Any]  # history cho LLM (role, content hoặc BaseMessage tuỳ layer)

    # ---- Tool / MCP results ----
    product_result: ProductResult | None
    service_result: ServiceResult | None
    order_result: OrderResult | None
    faq_result: FaqResult | None

    # ---- Reply generation ----
    draft_reply: str | None  # LLM draft
    final_reply: str | None  # gửi ra client
    need_human: bool | None
    human_note: str | None  # note cho nhân viên

    # ---- Error & meta ----
    error: ErrorInfo | None
    meta: dict | None  # log, latency, debug info

    # ---- Orchestrator / routing meta (tuỳ chọn, dùng cho LangGraph orchestrator) ----
    access: int | None
    agent_type: str | None
    context: dict | None
    llm: Any | None
    thread_id: str | None
    # user_input: bản text đã chuẩn hoá mà orchestrator/planner sử dụng.
    user_input: str | None
