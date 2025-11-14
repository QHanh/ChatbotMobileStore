"""Orchestrator ReAct mới dùng MCP + LangGraph.

Module này KHÔNG đụng vào logic /chat cũ. Mục tiêu:
- Nhận vào: tenant_id, user_input, history, access, effective MCP config.
- Dùng LLM (theo cấu hình tenant) + LangGraph để lập kế hoạch (planner) và chọn Agent phù hợp.
- Mỗi Agent là một node riêng, implement trong mcp/agents/*_agent.py.
- MCP tools được load qua langchain-mcp-adapters (MultiServerMCPClient) dựa trên cấu hình DB.

Giai đoạn này chỉ là skeleton, chưa nối với API /chat-mcp.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_mcp_adapters.client import MultiServerMCPClient

from sqlalchemy.orm import Session

from database.database import Customer
from mcp.services import MCPClientManager
from mcp.models import EffectiveTenantConfig
from .base import AgentContext, AgentResult


class OrchestratorState(TypedDict):
    """State cho LangGraph orchestrator.

    - messages: lịch sử message hiện tại (System + lịch sử + lượt hỏi hiện tại + quan sát).
    - tenant_id: định danh tenant.
    - access: quyền truy cập hiện tại.
    - agent_type: agent được planner chọn (vision/product/service/accessory/faq/knowledge/... ).
    - context: thông tin bổ sung cho agent (bindings, defaults...).
    """

    messages: List[BaseMessage]
    tenant_id: str
    access: Optional[int]
    agent_type: Optional[str]
    context: Dict[str, Any]


def _build_llm_for_customer(customer: Customer, api_key: str):
    """Khởi tạo LLM cho tenant dựa trên cấu hình trong bảng customers.

    - Nếu customer.llm_provider/llm_model không có, fallback về logic cũ:
      google_genai → gemini-2.5-flash, openai → gpt-4o-mini.
    """
    if not api_key:
        raise ValueError("Bạn chưa thêm API key bên trang cấu hình.")

    provider = customer.llm_provider or "google_genai"
    model = customer.llm_model

    if not model:
        if provider == "google_genai":
            model = "gemini-2.5-flash"
        elif provider == "openai":
            model = "gpt-4o-mini"
        else:
            raise ValueError(f"Không tìm thấy LLM provider: {provider}")

    llm = init_chat_model(model=model, model_provider=provider, api_key=api_key)
    return llm


async def _build_mcp_tools_for_tenant(
    db: Session,
    tenant_id: str,
    effective_config: EffectiveTenantConfig,
) -> List[Any]:
    """Tạo MultiServerMCPClient và load toàn bộ MCP tools cho tenant.

    Skeleton:
    - Đọc danh sách MCP servers từ cấu hình DB (thông qua MCPClientManager nếu cần).
    - Khởi tạo MultiServerMCPClient với mapping {server_name: {command/url, transport, ...}}.
    - Gọi client.get_tools() để lấy danh sách LangChain tools.

    Giai đoạn này chỉ là khung, chưa filter tool theo agent_type.
    """
    # TODO: build server_configs từ bảng mcp_servers / agent_bindings cho tenant.
    server_configs: Dict[str, Dict[str, Any]] = {}

    # Ví dụ cấu trúc (comment minh hoạ, không dùng trực tiếp):
    # server_configs = {
    #     "retrieval": {"url": "http://localhost:8001/mcp", "transport": "streamable_http"},
    #     "vision": {"command": "python", "args": ["/path/to/vision_server.py"], "transport": "stdio"},
    # }

    client = MultiServerMCPClient(server_configs)
    tools = await client.get_tools()
    return tools


def _planner_node(state: OrchestratorState, model) -> OrchestratorState:
    """Node planner: dùng LLM để chọn agent_type dựa trên messages + access.

    Skeleton: hiện tại planner chỉ dùng một prompt đơn giản để chọn agent,
    sau này có thể tinh chỉnh thêm prompt/rule.
    """
    messages = state["messages"]
    access = state.get("access")

    system = SystemMessage(
        content=(
            "Bạn là planner, nhiệm vụ: CHỈ trả về tên agent cần dùng trong một từ khóa duy nhất, "
            "trong danh sách: vision, product, service, accessory, faq, knowledge, store_info, "
            "customer_info, order, escalation, closing. Không giải thích thêm.\n"
            "Dựa trên câu hỏi cuối cùng và history, hãy chọn agent phù hợp nhất."
        )
    )

    last_message: Optional[BaseMessage] = messages[-1] if messages else None
    planner_messages: List[BaseMessage] = [system]
    if last_message is not None:
        planner_messages.append(last_message)

    ai: AIMessage = model.invoke(planner_messages)  # type: ignore[assignment]
    raw = (ai.content or "").strip().lower() if isinstance(ai, AIMessage) else ""

    # Đơn giản hoá: lấy token đầu tiên, fallback về "product" nếu không hợp lệ.
    agent_type = raw.split()[0] if raw else "product"

    next_state: OrchestratorState = {
        **state,
        "agent_type": agent_type,
    }
    return next_state


def _route_from_planner(state: OrchestratorState) -> str:
    """Hàm route dùng cho add_conditional_edges từ node planner."""
    agent_type = state.get("agent_type") or "product"
    # Map agent_type về tên node trong graph
    mapping = {
        "vision": "vision_agent",
        "product": "product_agent",
        "service": "service_agent",
        "accessory": "accessory_agent",
        "faq": "faq_agent",
        "knowledge": "knowledge_agent",
        "store_info": "store_info_agent",
        "customer_info": "customer_info_agent",
        "order": "order_agent",
        "escalation": "escalation_agent",
        "closing": "closing_agent",
    }
    return mapping.get(agent_type, "product_agent")


async def run_orchestrator_react(
    db: Session,
    tenant_id: str,
    user_input: str,
    history: List[BaseMessage],
    access: Optional[int],
    api_key: str,
    effective_config: EffectiveTenantConfig,
    mcp_client_manager: MCPClientManager,
) -> AgentResult:
    """Điểm vào chính cho orchestrator ReAct dùng MCP.

    Hàm này sẽ:
    - Khởi tạo LLM theo cấu hình tenant (customers.llm_provider/llm_model).
    - Load MCP tools thông qua MultiServerMCPClient.
    - Xây dựng LangGraph StateGraph với planner + các node agent.
    - Chạy graph một lần cho user_input hiện tại và trả về AgentResult.

    Giai đoạn đầu: triển khai skeleton, chưa gắn chặt với từng agent cụ thể.
    """
    customer = db.query(Customer).filter(Customer.customer_id == tenant_id).first()
    if not customer:
        raise ValueError(f"Không tìm thấy khách hàng: {tenant_id}")

    llm = _build_llm_for_customer(customer, api_key)
    tools = await _build_mcp_tools_for_tenant(db, tenant_id, effective_config)

    # Khởi tạo state ban đầu
    initial_messages: List[BaseMessage] = [HumanMessage(content=user_input)]
    initial_state: OrchestratorState = {
        "messages": initial_messages,
        "tenant_id": tenant_id,
        "access": access,
        "agent_type": None,
        "context": {},
    }

    # Xây dựng graph skeleton
    builder = StateGraph(OrchestratorState)

    # Node planner
    def planner_wrapper(state: OrchestratorState) -> OrchestratorState:
        return _planner_node(state, llm)

    builder.add_node("planner", planner_wrapper)

    # Node tools chung (dùng ToolNode để minh hoạ gọi MCP tools trực tiếp)
    tool_node = ToolNode(tools)

    def tools_node_wrapper(state: OrchestratorState) -> OrchestratorState:
        # Chạy tools_condition để quyết định có cần gọi tool hay không.
        # Ở skeleton này, ta luôn cho phép gọi tool một lần.
        result = tool_node.invoke({"messages": state["messages"]})
        messages = result.get("messages", [])
        return {
            **state,
            "messages": messages,
        }

    # Gắn tạm tất cả agent node về cùng một implementation chung cho skeleton.
    for node_name in [
        "vision_agent",
        "product_agent",
        "service_agent",
        "accessory_agent",
        "faq_agent",
        "knowledge_agent",
        "store_info_agent",
        "customer_info_agent",
        "order_agent",
        "escalation_agent",
        "closing_agent",
    ]:
        builder.add_node(node_name, tools_node_wrapper)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", _route_from_planner)

    # Mặc định, sau khi chạy agent node xong thì kết thúc.
    for node_name in [
        "vision_agent",
        "product_agent",
        "service_agent",
        "accessory_agent",
        "faq_agent",
        "knowledge_agent",
        "store_info_agent",
        "customer_info_agent",
        "order_agent",
        "escalation_agent",
        "closing_agent",
    ]:
        builder.add_edge(node_name, END)

    graph = builder.compile()

    final_state: OrchestratorState = await graph.ainvoke(initial_state)
    final_messages = final_state.get("messages", [])

    # Lấy câu trả lời cuối cùng từ chuỗi messages
    answer = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            answer = msg.content.strip()
            break

    return AgentResult(answer=answer, observations=[], used_tools=[])
