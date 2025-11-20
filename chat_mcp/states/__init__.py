"""Các định nghĩa state (TypedDict) dùng chung cho các workflow LangGraph.

Module này gom các kiểu state nhỏ (Intent, ProductResult, ...) và các state tổng
hợp như ChatState để có thể tái sử dụng giữa nhiều graph/node.
"""

from .chat_state import (
    Intent,
    ProductResult,
    ServiceResult,
    OrderResult,
    FaqResult,
    ErrorInfo,
    ChatState,
)

__all__ = [
    "Intent",
    "ProductResult",
    "ServiceResult",
    "OrderResult",
    "FaqResult",
    "ErrorInfo",
    "ChatState",
]
