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
from langchain_core.runnables import RunnableConfig
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


def _get_messages_from_state(state: OrchestratorState) -> List[BaseMessage]:
    messages = state.get("messages")
    if messages is None:
        inner = state.get("input")
        if isinstance(inner, dict):
            messages = inner.get("messages")
    # Nếu vẫn không có, coi như không có history, trả về list rỗng thay vì raise lỗi
    if messages is None:
        return []
    if not isinstance(messages, list):
        # Trường hợp hiếm: nếu là một message đơn lẻ, bọc thành list; nếu kiểu khác, trả về rỗng
        from langchain_core.messages import BaseMessage as _BM  # tránh import vòng
        if isinstance(messages, _BM):
            return [messages]
        return []
    return messages


def _get_context_from_state(state: OrchestratorState) -> Dict[str, Any]:
    """Lấy context từ state hoặc từ state['input'] nếu LangGraph bọc state.

    Luôn trả về dict (có thể rỗng) để tránh lỗi None.
    """

    context = state.get("context")
    if context is None:
        inner = state.get("input")
        if isinstance(inner, dict):
            context = inner.get("context")
    if not isinstance(context, dict):
        return {}
    return context


def _get_tenant_id_from_state(state: OrchestratorState) -> str:
    """Lấy tenant_id từ state, hoặc từ input/context nếu cần.

    Nếu không tìm được tenant_id hợp lệ, raise ValueError để upstream trả 400.
    """

    tenant_id: Optional[str] = state.get("tenant_id")  # type: ignore[assignment]
    if not tenant_id:
        inner = state.get("input")
        if isinstance(inner, dict):
            tenant_id = inner.get("tenant_id")  # type: ignore[assignment]
    if not tenant_id:
        ctx = _get_context_from_state(state)
        raw_tid = ctx.get("tenant_id")
        if isinstance(raw_tid, str) and raw_tid:
            tenant_id = raw_tid

    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("Missing tenant_id in orchestrator state")

    return tenant_id


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
    ai_name = customer.ai_name or ""
    ai_role = customer.ai_role or ""

    def _default_agent_prompt(agent_type: str) -> str:
        """Default prompt riêng cho từng agent_type khi DB chưa cấu hình agent.{agent_type}.system_prompt.

        Mặc định dùng base_prompt rồi bổ sung mô tả vai trò/nghiệp vụ cho từng agent.
        """

        suffix = ""
        if agent_type == "product":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO PRODUCT AGENT]\n"
                "Bạn là Product Agent, chuyên tư vấn và tra cứu SẢN PHẨM CHÍNH (điện thoại, máy tính, thiết bị chính). "
                "Hãy ưu tiên sử dụng các công cụ tìm kiếm sản phẩm (ví dụ: products_search) và tập trung vào mã sản phẩm, model, cấu hình, giá, tồn kho. "
                "Các câu hỏi thuần về PHỤ KIỆN/LINH KIỆN nên được xử lý bởi Accessory Agent."
            )
        elif agent_type == "service":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO SERVICE AGENT]\n"
                "Bạn là Service Agent, chuyên tư vấn và tra cứu DỊCH VỤ SỬA CHỮA, bảo hành, dịch vụ kỹ thuật. "
                "Hãy ưu tiên dùng các công cụ tìm kiếm dịch vụ (ví dụ: services_search). "
                "Các câu hỏi thuần về phụ kiện/máy móc nên do Accessory Agent xử lý, còn câu hỏi về sản phẩm chính do Product Agent xử lý."
            )
        elif agent_type == "accessory":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO ACCESSORY AGENT]\n"
                "Bạn là Accessory Agent, chuyên tư vấn và tra cứu PHỤ KIỆN / LINH KIỆN / ĐỒ NGHỀ (ví dụ: dây cáp, củ sạc, ốp lưng, máy hàn, máy khò, dụng cụ sửa chữa...). "
                "Luôn ưu tiên sử dụng công cụ tìm kiếm phụ kiện (ví dụ: accessories_search). "
                "Khi câu hỏi chứa các cụm đặc trưng về phụ kiện hoặc máy móc (brand + model/mã), hãy coi đây là yêu cầu chính của bạn."
            )
        elif agent_type == "faq":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO FAQ AGENT]\n"
                "Bạn là FAQ Agent, ưu tiên sử dụng ngữ cảnh FAQ được cung cấp để trả lời các câu hỏi lặp lại, chính sách, hướng dẫn chung."
            )
        elif agent_type == "knowledge":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO KNOWLEDGE AGENT]\n"
                "Bạn là Knowledge Agent, chuyên tổng hợp kiến thức sâu, giải thích chi tiết, hoặc trả lời các câu hỏi cần suy luận nhiều bước dựa trên nguồn tri thức (ví dụ GraphRAG)."
            )
        elif agent_type == "store_info":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO STORE_INFO AGENT]\n"
                "Bạn là Store Info Agent, chuyên trả lời các câu hỏi về cửa hàng: địa chỉ, số điện thoại, website, Facebook, bản đồ, chính sách."
            )
        elif agent_type == "customer_info":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO CUSTOMER_INFO AGENT]\n"
                "Bạn là Customer Info Agent, chuyên kiểm tra và nhắc khách bổ sung thông tin cá nhân cần thiết để tạo đơn hàng (tên, số điện thoại, địa chỉ, ...)."
            )
        elif agent_type == "order":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO ORDER AGENT]\n"
                "Bạn là Order Agent, chuyên hỗ trợ CHỐT ĐƠN và tạo đơn hàng (sản phẩm, dịch vụ, phụ kiện) bằng các công cụ tạo đơn tương ứng."
            )
        elif agent_type == "escalation":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO ESCALATION AGENT]\n"
                "Bạn là Escalation Agent, chuyên xử lý các tình huống cần chuyển cho người thật, khi khách phàn nàn hoặc yêu cầu hỗ trợ trực tiếp."
            )
        elif agent_type == "closing":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO CLOSING AGENT]\n"
                "Bạn là Closing Agent, chuyên xử lý các lời chào tạm biệt / kết thúc hội thoại, cảm ơn khách và kết thúc cuộc trò chuyện một cách tự nhiên."
            )
        elif agent_type == "vision":
            suffix = (
                "\n\n[HƯỚNG DẪN RIÊNG CHO VISION AGENT]\n"
                "Bạn là Vision Agent, chuyên nhận diện sản phẩm hoặc nội dung từ ảnh (image_urls hoặc image_base64) và trả kết quả dạng văn bản để agent khác sử dụng."
            )

        if suffix:
            return suffix.lstrip()
        return "Bạn là trợ lý AI hỗ trợ khách hàng. Hãy trả lời thân thiện, ngắn gọn và đúng vai trò agent của bạn."

    def _for(agent_type: str) -> str:
        key = f"agent.{agent_type}.system_prompt"
        text = instr.get(key)
        if text:
            text = text.replace("{ai_name}", ai_name).replace("{ai_role}", ai_role)
            return text.strip()
        return _default_agent_prompt(agent_type)

    prompts: Dict[str, str] = {}
    for t in AGENT_NODE_MAPPING.keys():
        prompts[t] = _for(t)

    # Debug: log toàn bộ system prompt cho orchestrator/agents để dễ debug routing.
    for agent_type, prompt in prompts.items():
        try:
            print(f"[ORCH] System prompt for agent_type={agent_type!r}:")
            print(prompt)
            print("[ORCH] ---- END SYSTEM PROMPT ----")
        except Exception:
            continue
    return prompts


def _planner_node(state: OrchestratorState, config: RunnableConfig) -> OrchestratorState:
    """Node planner: dùng LLM để chọn agent_type dựa trên messages + access.

    Skeleton: hiện tại planner chỉ dùng một prompt đơn giản để chọn agent,
    sau này có thể tinh chỉnh thêm prompt/rule.
    """
    # Lấy runtime config (per-request) từ RunnableConfig.configurable.
    configurable: Dict[str, Any] = {}
    try:
        configurable = (config or {}).get("configurable") or {}
    except Exception:
        configurable = {}

    messages = _get_messages_from_state(state)
    access = configurable.get("access", state.get("access"))
    context = _get_context_from_state(state)
    model = configurable.get("llm") or context.get("llm") or state.get("llm")

    # Debug: xem state + config mà planner nhận được có đủ key không.
    try:
        print("[ORCH-PLANNER] state_in_keys=", list(state.keys()))
        print("[ORCH-PLANNER] configurable_keys=", list(configurable.keys()))
    except Exception:
        pass

    # Xác định danh sách agent được phép dựa trên access.
    # Lưu ý: hiện tại /chat-mcp chỉ dùng input dạng text, nên planner không cần chọn vision agent.
    all_agents: List[str] = [
        "product",
        "service",
        "accessory",
        "faq",
        "knowledge",
        "store_info",
        "customer_info",
        "order",
        "escalation",
        "closing",
    ]

    allowed_agents: List[str] = list(all_agents)

    if isinstance(access, int) and access != 100:
        access_str = str(access)
        main_agents: List[str] = []
        if "1" in access_str:
            main_agents.append("product")
        if "2" in access_str:
            main_agents.append("service")
        if "3" in access_str:
            main_agents.append("accessory")

        secondary_agents: List[str] = [
            "faq",
            "knowledge",
            "store_info",
            "customer_info",
            "order",
            "escalation",
            "closing",
        ]

        allowed_agents = []
        # Vision luôn được phép nếu tồn tại.
        if "vision" in all_agents:
            allowed_agents.append("vision")
        # Thêm các agent chính theo access.
        for a in main_agents:
            if a in all_agents and a not in allowed_agents:
                allowed_agents.append(a)
        # Thêm các agent phụ.
        for a in secondary_agents:
            if a in all_agents and a not in allowed_agents:
                allowed_agents.append(a)

    if not allowed_agents:
        allowed_agents = all_agents

    allowed_str = ", ".join(allowed_agents)

    # Lấy text câu hỏi cuối cùng để áp dụng một số rule đơn giản.
    last_message: Optional[BaseMessage] = messages[-1] if messages else None
    last_text = ""

    # 1) Ưu tiên lấy từ HumanMessage cuối cùng nếu có.
    if isinstance(last_message, HumanMessage) and isinstance(last_message.content, str):
        raw = (last_message.content or "").strip()
        if raw:
            last_text = raw.lower()

    # 2) Nếu vẫn trống, tìm embedded user_input trong SystemMessage.
    if not last_text:
        for msg in messages:
            if isinstance(msg, SystemMessage) and isinstance(msg.content, str):
                content = msg.content
                if "[INTERNAL_USER_INPUT]" in content and "[/INTERNAL_USER_INPUT]" in content:
                    start = content.find("[INTERNAL_USER_INPUT]") + len("[INTERNAL_USER_INPUT]")
                    end = content.find("[/INTERNAL_USER_INPUT]")
                    if start < end:
                        embedded_ui = content[start:end].strip()
                        if embedded_ui:
                            last_text = embedded_ui.lower()
                            break

    # 3) Fallback cuối: config/state keys.
    if not last_text:
        raw_ui: Any = configurable.get("user_input")
        if not isinstance(raw_ui, str) or not raw_ui.strip():
            raw_ui = state.get("user_input")
        if not isinstance(raw_ui, str) or not raw_ui.strip():
            inner = state.get("input")
            if isinstance(inner, dict):
                raw_ui = inner.get("user_input")
        if not isinstance(raw_ui, str) or not raw_ui.strip():
            raw_ctx = context.get("raw_user_input")
            if isinstance(raw_ctx, str) and raw_ctx.strip():
                raw_ui = raw_ctx
        if not isinstance(raw_ui, str) or not raw_ui.strip():
            meta = context.get("metadata") or {}
            if isinstance(meta, dict):
                meta_ui = meta.get("user_input")
                if isinstance(meta_ui, str) and meta_ui.strip():
                    raw_ui = meta_ui
        if isinstance(raw_ui, str) and raw_ui.strip():
            last_text = raw_ui.strip().lower()

    print(
        f"[ORCH-PLANNER] Debug: allowed_agents={allowed_agents}, "
        f"last_text={last_text!r}"
    )

    # Shortcut: nếu rõ ràng là hỏi về phụ kiện/máy hàn/máy khò và accessory được phép, chọn luôn 'accessory'.
    if last_text and "accessory" in allowed_agents:
        accessory_keywords = [
            "phu kien",
            "phụ kiện",
            "linh kien",
            "linh kiện",
            "may han",
            "máy hàn",
            "may kho",
            "máy khò",
            "mo han",
            "mỏ hàn",
        ]
        for kw in accessory_keywords:
            if kw in last_text:
                agent_type = "accessory"
                print(
                    "[ORCH-PLANNER] Shortcut: detected accessory intent via keyword '",
                    kw,
                    "' -> agent_type='accessory'",
                )
                next_state: OrchestratorState = {**state, "agent_type": agent_type}
                print(f"[ORCH] Planner selected agent_type={agent_type!r} (via shortcut)")
                return next_state

    # Nếu thiếu LLM trong context, fallback ưu tiên 'accessory' nếu được phép.
    if model is None:
        if "accessory" in allowed_agents:
            agent_type = "accessory"
        else:
            agent_type = allowed_agents[0] if allowed_agents else "product"
    else:
        system = SystemMessage(
            content=(
                "Bạn là planner, nhiệm vụ: dựa trên câu hỏi của khách, chọn MỘT agent phù hợp nhất "
                "trong danh sách sau và CHỈ trả về tên agent đó (không giải thích thêm): "
                f"{allowed_str}.\n"
                "Mô tả ngắn:\n"
                "- product: tư vấn sản phẩm chính (điện thoại, laptop, thiết bị chính, ...).\n"
                "- service: tư vấn dịch vụ sửa chữa, bảo hành, ép kính, ...\n"
                "- accessory: tư vấn phụ kiện / linh kiện / đồ nghề (dây cáp, củ sạc, máy hàn, máy khò, ...).\n"
                "- faq: câu hỏi thường gặp, chính sách.\n"
                "- knowledge: giải thích kiến thức, tổng hợp thông tin.\n"
                "- order: chốt đơn / tạo đơn hàng.\n"
                "- escalation: chuyển cho người thật khi cần.\n"
                "- closing: kết thúc hội thoại một cách lịch sự.\n"
                "\nQUY TẮC BẮT BUỘC:\n"
                "- Nếu câu hỏi liên quan đến phụ kiện / linh kiện / đồ nghề / máy hàn / máy khò / mỏ hàn, "
                "hoặc các thiết bị phụ trợ tương tự, BẮT BUỘC chọn agent 'accessory' (nếu nó có trong danh sách cho phép).\n"
                "- Nếu câu hỏi liên quan đến dịch vụ sửa chữa, bảo hành, ép kính, thay thế linh kiện, BẮT BUỘC chọn agent 'service' "
                "(nếu nó có trong danh sách cho phép).\n"
                "- Nếu câu hỏi là hỏi mua sản phẩm chính (điện thoại, máy tính, thiết bị chính) mà không rơi vào hai trường hợp trên, chọn agent 'product' "
                "(nếu nó có trong danh sách cho phép).\n"
                "\nVÍ DỤ:\n"
                "- Câu hỏi: 'có máy hàn quick không' hoặc 'có phụ kiện máy hàn nào không' -> Trả về: accessory\n"
                "- Câu hỏi: 'bên mình có thay màn hình iPhone 12 không' -> Trả về: service\n"
                "- Câu hỏi: 'có iPhone 15 Pro Max không' -> Trả về: product\n"
                "\nCHỈ trả về đúng một từ: tên agent trong danh sách trên, viết thường."
            )
        )

        # Debug: log system prompt của planner + message cuối cùng.
        try:
            print("[ORCH-PLANNER] System prompt used for planner:")
            print(system.content)
        except Exception:
            pass

        last_message: Optional[BaseMessage] = messages[-1] if messages else None
        if last_message is not None:
            try:
                print(
                    f"[ORCH-PLANNER] Last message before planning: type={type(last_message).__name__}, "
                    f"content={getattr(last_message, 'content', last_message)}"
                )
            except Exception:
                pass

        planner_messages: List[BaseMessage] = [system]
        if last_message is not None:
            planner_messages.append(last_message)

        ai: AIMessage = model.invoke(planner_messages)  # type: ignore[assignment]
        raw = (ai.content or "").strip().lower() if isinstance(ai, AIMessage) else ""

        try:
            print(f"[ORCH-PLANNER] LLM raw planner output={raw!r}")
        except Exception:
            pass

        # Đơn giản hoá: lấy token đầu tiên, fallback ưu tiên 'accessory' nếu không hợp lệ.
        candidate = raw.split()[0] if raw else ""
        if candidate in allowed_agents:
            agent_type = candidate
        else:
            if "accessory" in allowed_agents:
                agent_type = "accessory"
            else:
                agent_type = allowed_agents[0] if allowed_agents else "product"

    print(f"[ORCH] Planner selected agent_type={agent_type!r}")
    next_state: OrchestratorState = {
        **state,
        "agent_type": agent_type,
    }
    try:
        print("[ORCH-PLANNER] state_out_keys=", list(next_state.keys()))
    except Exception:
        pass
    return next_state


def _route_from_planner(state: OrchestratorState) -> str:
    """Hàm route dùng cho add_conditional_edges từ node planner."""
    agent_type = state.get("agent_type") or "product"
    # Map agent_type về tên node trong graph
    node_name = AGENT_NODE_MAPPING.get(agent_type, "product_agent")
    print(f"[ORCH] Routing to node={node_name!r} for agent_type={agent_type!r}")
    return node_name


def _make_agent_node_factory_for_tenant(tenant_id: str):
    """Tạo AgentNodeFactory cho một tenant cụ thể, capture tenant_id qua closure.

    Điều này giúp không phụ thuộc vào việc LangGraph có giữ tenant_id trong state hay không.
    """

    def factory(agent_type: str, tools_for_agent: List[Any]):
        AgentCls = AGENT_CLASS_MAPPING.get(agent_type)
        print(f"[ORCH] Creating agent node for agent_type={agent_type!r} with {len(tools_for_agent)} tools")

        async def node_fn(state: OrchestratorState, config: RunnableConfig) -> OrchestratorState:
            # Debug: xem state mà agent node nhận được sau planner.
            try:
                print(
                    f"[ORCH-AGENT] entry state keys for agent_type={agent_type!r}: "
                    f"{list(state.keys())}"
                )
            except Exception:
                pass

            # Lấy runtime config cho request hiện tại.
            configurable: Dict[str, Any] = {}
            try:
                configurable = (config or {}).get("configurable") or {}
            except Exception:
                configurable = {}

            messages = list(_get_messages_from_state(state))
            context = _get_context_from_state(state)
            agent_prompts_ctx = context.get("agent_prompts", {})
            system_prompt = agent_prompts_ctx.get(agent_type, "")

            history_messages: List[BaseMessage] = messages[:-1] if messages else []
            last_message: Optional[BaseMessage] = messages[-1] if messages else None
            user_input = ""
            if isinstance(last_message, HumanMessage) and isinstance(last_message.content, str):
                user_input = last_message.content or ""
            elif last_message is not None:
                content = getattr(last_message, "content", "")
                if isinstance(content, str):
                    user_input = content

            # Fallback: nếu vẫn chưa có user_input, tìm từ embedded SystemMessage.
            if not user_input:
                for msg in messages:
                    if isinstance(msg, SystemMessage) and isinstance(msg.content, str):
                        content = msg.content
                        if "[INTERNAL_USER_INPUT]" in content and "[/INTERNAL_USER_INPUT]" in content:
                            start = content.find("[INTERNAL_USER_INPUT]") + len("[INTERNAL_USER_INPUT]")
                            end = content.find("[/INTERNAL_USER_INPUT]")
                            if start < end:
                                embedded_ui = content[start:end].strip()
                                if embedded_ui:
                                    user_input = embedded_ui
                                    break

            # Fallback cuối: config/state keys.
            if not user_input:
                raw_ui: Any = configurable.get("user_input")
                if not isinstance(raw_ui, str) or not raw_ui.strip():
                    raw_ui = state.get("user_input")
                if not isinstance(raw_ui, str) or not raw_ui.strip():
                    inner = state.get("input")
                    if isinstance(inner, dict):
                        raw_ui = inner.get("user_input")
                if not isinstance(raw_ui, str) or not raw_ui.strip():
                    raw_ctx = context.get("raw_user_input")
                    if isinstance(raw_ctx, str) and raw_ctx.strip():
                        raw_ui = raw_ctx
                if not isinstance(raw_ui, str) or not raw_ui.strip():
                    meta = context.get("metadata") or {}
                    if isinstance(meta, dict):
                        meta_ui = meta.get("user_input")
                        if isinstance(meta_ui, str) and meta_ui.strip():
                            raw_ui = meta_ui
                if isinstance(raw_ui, str):
                    user_input = raw_ui

            try:
                print(
                    f"[ORCH-AGENT] agent_type={agent_type!r} resolved user_input={user_input!r}, "
                    f"state_user_input={state.get('user_input')!r}"
                )
            except Exception:
                pass

            if AgentCls is not None:
                print(
                    f"[ORCH] Running agent={AgentCls.__name__} for agent_type={agent_type!r} "
                    f"(tenant_id={tenant_id}) with {len(tools_for_agent)} tools"
                )

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
            if not thread_id:
                thread_id = state.get("thread_id")
            if not thread_id:
                inner = state.get("input")
                if isinstance(inner, dict):
                    thread_id = inner.get("thread_id")
            if not thread_id:
                thread_id = configurable.get("thread_id")
            if thread_id:
                metadata.setdefault("thread_id", thread_id)
            llm_obj = context.get("llm")
            if llm_obj is not None:
                metadata.setdefault("llm", llm_obj)
            if system_prompt:
                metadata.setdefault("system_prompt", system_prompt)
            metadata.setdefault("tenant_id", tenant_id)

            # Đảm bảo metadata cũng mang theo user_input để agent dùng khi cần.
            if "user_input" not in metadata and user_input:
                metadata["user_input"] = user_input

            try:
                print(
                    f"[ORCH-AGENT] agent_type={agent_type!r} metadata.thread_id={metadata.get('thread_id')!r}, "
                    f"state_thread_id={state.get('thread_id')!r}, context_thread_id={context.get('thread_id')!r}"
                )
            except Exception:
                pass

            agent_context = AgentContext(
                tenant_id=tenant_id,
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

    return factory


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
    print(
        f"[ORCH] run_orchestrator_react called for tenant_id={tenant_id!r}, "
        f"thread_id={thread_id!r}, history_len={len(history)}"
    )

    try:
        print(f"[ORCH] run_orchestrator_react raw user_input={user_input!r}")
    except Exception:
        pass

    customer = db.query(Customer).filter(Customer.customer_id == tenant_id).first()
    if not customer:
        raise ValueError(f"Không tìm thấy khách hàng: {tenant_id}")


    llm = _build_llm_for_customer(customer, api_key)
    print("[ORCH] LLM for customer initialized")

    config_version = customer.config_version or 0
    cache_key = f"{tenant_id}:{config_version}"
    print(f"[ORCH] Using orchestrator cache_key={cache_key!r}")

    initial_messages: List[BaseMessage] = []
    if history:
        initial_messages.extend(list(history))
    
    # Đảm bảo user_input luôn có trong messages dưới dạng HumanMessage cuối cùng.
    human_msg = HumanMessage(content=user_input)
    initial_messages.append(human_msg)
    
    # WORKAROUND: LangGraph có thể không truyền state keys vào node đúng cách,
    # nên mình cũng embed user_input vào một SystemMessage ẩn để node đọc được.
    embedded_system = SystemMessage(content=f"[INTERNAL_USER_INPUT]{user_input}[/INTERNAL_USER_INPUT]")
    initial_messages.insert(0, embedded_system)

    agent_prompts = _build_agent_prompt_map(db, customer)
    print(f"[ORCH] Built agent_prompts for agent_types={list(agent_prompts.keys())}")

    print("[ORCH] Calling get_or_build_graph ...")
    graph = await get_or_build_graph(
        cache_key=cache_key,
        effective_config=effective_config,
        agent_node_mapping=AGENT_NODE_MAPPING,
        planner_node=_planner_node,
        route_from_planner=_route_from_planner,
        agent_node_factory=_make_agent_node_factory_for_tenant(tenant_id),
    )
    print("[ORCH] Graph object ready, building initial_state")

    initial_state: OrchestratorState = {
        "messages": initial_messages,
        "tenant_id": tenant_id,
        "thread_id": thread_id,
        "user_input": user_input,
        "access": access,
        "agent_type": None,
        "llm": llm,
        "context": {
            "llm": llm,
            "agent_prompts": agent_prompts,
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "raw_user_input": user_input,
            # Bơm sẵn metadata để các node có thể đọc được ngay cả khi state bị wrap.
            "metadata": {
                "thread_id": thread_id or "",
                "user_input": user_input or "",
            },
        },
    }

    try:
        ctx0 = initial_state.get("context", {}) or {}
        print(
            f"[ORCH] initial_state.user_input={initial_state.get('user_input')!r}, "
            f"context.raw_user_input={ctx0.get('raw_user_input')!r}"
        )
    except Exception:
        pass

    runtime_config: RunnableConfig = {
        "configurable": {
            "tenant_id": tenant_id,
            "thread_id": thread_id or "",
            "user_input": user_input,
            "access": access,
            "llm": llm,
        }
    }

    print(
        f"[ORCH] Invoking graph.ainvoke with messages_len={len(initial_messages)}, "
        f"access={access}, tenant_id={tenant_id!r}, configurable_keys={list(runtime_config['configurable'].keys())}"
    )
    final_state: OrchestratorState = await graph.ainvoke(initial_state, config=runtime_config)
    print("[ORCH] Graph execution finished, processing final_state")
    final_messages = final_state.get("messages", [])

    # Lấy câu trả lời cuối cùng từ chuỗi messages
    answer = ""
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            answer = msg.content.strip()
            break

    print(f"[ORCH] Returning AgentResult with answer_len={len(answer)}")
    return AgentResult(answer=answer, observations=[], used_tools=[])


async def prewarm_tenant_graph(
    db: Session,
    tenant_id: str,
    effective_config: EffectiveTenantConfig,
) -> None:
    print(f"[ORCH] prewarm_tenant_graph called for tenant_id={tenant_id!r}")
    customer = db.query(Customer).filter(Customer.customer_id == tenant_id).first()
    if not customer:
        print(f"[ORCH] prewarm_tenant_graph: customer {tenant_id!r} not found, skip prewarm")
        return
    config_version = customer.config_version or 0
    cache_key = f"{tenant_id}:{config_version}"
    print(f"[ORCH] prewarm_tenant_graph using cache_key={cache_key!r}")
    await get_or_build_graph(
        cache_key=cache_key,
        effective_config=effective_config,
        agent_node_mapping=AGENT_NODE_MAPPING,
        planner_node=_planner_node,
        route_from_planner=_route_from_planner,
        agent_node_factory=_make_agent_node_factory_for_tenant(tenant_id),
    )
