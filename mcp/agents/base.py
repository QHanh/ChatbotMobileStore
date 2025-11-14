from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage


@dataclass
class AgentContext:
    """Ngữ cảnh chuẩn truyền vào cho mỗi Agent trong kiến trúc MCP.

    - tenant_id: định danh khách hàng/tenant.
    - user_input: câu hỏi hiện tại của người dùng (đã xử lý ảnh nếu có).
    - history: lịch sử hội thoại dạng message cho LLM.
    - bindings: cấu hình MCP hiệu lực cho agent hoặc tenant (AgentBinding/EffectiveConfig).
    - defaults: tham số mặc định cho agent/tool (từ MCP bindings).
    - access: quyền truy cập (1: sản phẩm, 2: dịch vụ, 3: phụ kiện, 123: full...).
    """

    tenant_id: str
    user_input: str
    history: List[BaseMessage] = field(default_factory=list)
    bindings: Any = None
    defaults: Dict[str, Any] = field(default_factory=dict)
    access: Optional[int] = None


@dataclass
class AgentResult:
    """Kết quả chuẩn mà mỗi Agent trả về cho orchestrator."""

    answer: str
    observations: List[str] = field(default_factory=list)
    used_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
