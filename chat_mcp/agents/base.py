from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import inspect

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
    tools: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Kết quả chuẩn mà mỗi Agent trả về cho orchestrator."""

    answer: str
    observations: List[str] = field(default_factory=list)
    used_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


async def call_mcp_tool(tools: List[Any], tool_name: str, args: Dict[str, Any]) -> Any:
    for tool in tools:
        name = getattr(tool, "name", None)
        if name != tool_name:
            continue
        try:
            ainvoke = getattr(tool, "ainvoke", None)
            if callable(ainvoke):
                return await ainvoke(args)
            invoke = getattr(tool, "invoke", None)
            if callable(invoke):
                result = invoke(args)
                if inspect.isawaitable(result):
                    return await result
                return result
            run = getattr(tool, "run", None)
            if callable(run):
                result = run(args)
                if inspect.isawaitable(result):
                    return await result
                return result
        except Exception as e:
            print(f"Error calling MCP tool '{tool_name}': {e}")
            return {"error": str(e)}
    return None

