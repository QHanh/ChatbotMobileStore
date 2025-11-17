"""Orchestrator ReAct mới dùng MCP + LangGraph.

Module này KHÔNG đụng vào logic /chat cũ. Mục tiêu:
- Nhận vào: tenant_id, user_input, history, access, effective MCP config.
- Dùng LLM (theo cấu hình tenant) + LangGraph để lập kế hoạch (planner) và chọn Agent phù hợp.
- Mỗi Agent là một node riêng, implement trong mcp/agents/*_agent.py.
- MCP tools được load qua langchain-mcp-adapters (MultiServerMCPClient) dựa trên cấu hình DB.

Giai đoạn này chỉ là skeleton, chưa nối với API /chat-mcp.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict

import shlex

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from sqlalchemy.orm import Session

from database.database import Customer
from chat_mcp.services import MCPClientManager
from chat_mcp.services.orchestrator_loader import get_or_build_graph
from chat_mcp.models import EffectiveAgentConfig, EffectiveTenantConfig, AgentBindingOut
from service.prompts.prompt_service import load_instructions, compose_system_prompt
from .base import AgentContext, AgentResult
from .product_agent import ProductAgent
from .service_agent import ServiceAgent
from .accessory_agent import AccessoryAgent
from .faq_agent import FAQAgent
from .knowledge_agent import KnowledgeAgent
from .vision_agent import VisionAgent
from .store_info_agent import StoreInfoAgent
from .customer_info_agent import CustomerInfoAgent
from .order_agent import OrderAgent
from .escalation_agent import EscalationAgent
from .closing_agent import ClosingAgent


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


AGENT_NODE_MAPPING: Dict[str, str] = {
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


AGENT_CLASS_MAPPING: Dict[str, Any] = {
    "vision": VisionAgent,
    "product": ProductAgent,
    "service": ServiceAgent,
    "accessory": AccessoryAgent,
    "faq": FAQAgent,
    "knowledge": KnowledgeAgent,
    "store_info": StoreInfoAgent,
    "customer_info": CustomerInfoAgent,
    "order": OrderAgent,
    "escalation": EscalationAgent,
    "closing": ClosingAgent,
}


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


def _build_agent_prompt_map(db: Session, customer: Customer) -> Dict[str, str]:
    """Xây map system prompt cho từng agent_type dựa trên SystemInstruction trong DB.

    Ưu tiên key dạng ``agent.{agent_type}.system_prompt``. Nếu không có, fallback về
    ``compose_system_prompt`` hiện tại (prompt tổng cho toàn hệ thống).
    """

    instr = load_instructions(db)
    base_prompt = compose_system_prompt(
        db=db,
        customer_config=customer,
        product_feature_enabled=True,
        service_feature_enabled=True,
        accessory_feature_enabled=True,
    )

    ai_name = customer.ai_name or ""
    ai_role = customer.ai_role or ""

    def _for(agent_type: str) -> str:
        key = f"agent.{agent_type}.system_prompt"
        text = instr.get(key)
        if text:
            text = text.replace("{ai_name}", ai_name).replace("{ai_role}", ai_role)
            return text.strip()
        return base_prompt

    prompts: Dict[str, str] = {}
    for t in AGENT_NODE_MAPPING.keys():
        prompts[t] = _for(t)
    return prompts


def _planner_node(state: OrchestratorState) -> OrchestratorState:
    """Node planner: dùng LLM để chọn agent_type dựa trên messages + access.

    Skeleton: hiện tại planner chỉ dùng một prompt đơn giản để chọn agent,
    sau này có thể tinh chỉnh thêm prompt/rule.
    """
    messages = state["messages"]
    access = state.get("access")
    context = state.get("context") or {}
    model = context.get("llm")
    if model is None:
        raise ValueError("Thiếu LLM trong context của orchestrator.")

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
    return AGENT_NODE_MAPPING.get(agent_type, "product_agent")


def _agent_node_factory(agent_type: str, tools_for_agent: List[Any]):
    AgentCls = AGENT_CLASS_MAPPING.get(agent_type)

    async def node_fn(state: OrchestratorState) -> OrchestratorState:
        messages = list(state["messages"])
        context = state.get("context") or {}
        agent_prompts_ctx = context.get("agent_prompts", {})
        system_prompt = agent_prompts_ctx.get(agent_type, "")

        history_messages: List[BaseMessage] = messages[:-1] if messages else []
        last_message: Optional[BaseMessage] = messages[-1] if messages else None
        user_input = ""
        if isinstance(last_message, HumanMessage):
            user_input = last_message.content or ""
        elif last_message is not None:
            content = getattr(last_message, "content", "")
            if isinstance(content, str):
                user_input = content

        if AgentCls is None:
            tool_node = ToolNode(tools_for_agent)
            effective_messages = messages
            if system_prompt:
                effective_messages = [SystemMessage(content=system_prompt)] + effective_messages
            result = tool_node.invoke({"messages": effective_messages})
            new_messages = result.get("messages", effective_messages)
            return {
                **state,
                "messages": new_messages,
            }

        metadata: Dict[str, Any] = {}
        raw_meta = context.get("metadata") or {}
        if isinstance(raw_meta, dict):
            metadata.update(raw_meta)
        thread_id = context.get("thread_id")
        if thread_id is not None:
            metadata.setdefault("thread_id", thread_id)
        llm_obj = context.get("llm")
        if llm_obj is not None:
            metadata.setdefault("llm", llm_obj)
        if system_prompt:
            metadata.setdefault("system_prompt", system_prompt)

        agent_context = AgentContext(
            tenant_id=state["tenant_id"],
            user_input=user_input,
            history=history_messages,
            bindings=None,
            defaults={},
            access=state.get("access"),
            tools=tools_for_agent,
            metadata=metadata,
        )

        agent = AgentCls()
        result: AgentResult = await agent.run(agent_context)  # type: ignore[call-arg]

        new_messages = list(messages)
        if result.answer:
            new_messages.append(AIMessage(content=result.answer))
        return {
            **state,
            "messages": new_messages,
        }

    return node_fn


async def run_orchestrator_react(
    db: Session,
    tenant_id: str,
    user_input: str,
    history: List[BaseMessage],
    access: Optional[int],
    api_key: str,
    effective_config: EffectiveTenantConfig,
    mcp_client_manager: MCPClientManager,
    thread_id: Optional[str] = None,
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
    config_version = customer.config_version or 0
    cache_key = f"{tenant_id}:{config_version}"

    initial_messages: List[BaseMessage] = []
    if history:
        initial_messages.extend(list(history))
    initial_messages.append(HumanMessage(content=user_input))

    agent_prompts = _build_agent_prompt_map(db, customer)

    graph = await get_or_build_graph(
        cache_key=cache_key,
        effective_config=effective_config,
        agent_node_mapping=AGENT_NODE_MAPPING,
        planner_node=_planner_node,
        route_from_planner=_route_from_planner,
        agent_node_factory=_agent_node_factory,
    )

    initial_state: OrchestratorState = {
        "messages": initial_messages,
        "tenant_id": tenant_id,
        "access": access,
        "agent_type": None,
        "context": {
            "llm": llm,
            "agent_prompts": agent_prompts,
            "thread_id": thread_id,
        },
    }

    final_state: OrchestratorState = await graph.ainvoke(initial_state)
    final_messages = final_state.get("messages", [])

    # Lấy câu trả lời cuối cùng từ chuỗi messages
    answer = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            answer = msg.content.strip()
            break

    return AgentResult(answer=answer, observations=[], used_tools=[])


async def prewarm_tenant_graph(
    db: Session,
    tenant_id: str,
    effective_config: EffectiveTenantConfig,
) -> None:
    customer = db.query(Customer).filter(Customer.customer_id == tenant_id).first()
    if not customer:
        return
    config_version = customer.config_version or 0
    cache_key = f"{tenant_id}:{config_version}"
    await get_or_build_graph(
        cache_key=cache_key,
        effective_config=effective_config,
        agent_node_mapping=AGENT_NODE_MAPPING,
        planner_node=_planner_node,
        route_from_planner=_route_from_planner,
        agent_node_factory=_agent_node_factory,
    )
