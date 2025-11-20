from typing import Any, Callable, Dict, List

import asyncio
import shlex
import inspect
from contextlib import AsyncExitStack

from langchain_core.messages import SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from chat_mcp.models import EffectiveTenantConfig
from chat_mcp.states import ChatState


State = ChatState
PlannerNodeFn = Callable[[State], State]
RouteFn = Callable[[State], str]
AgentNodeFactory = Callable[[str, List[Any]], Callable[[State], Any]]

_GRAPH_CACHE: Dict[str, Any] = {}
_GRAPH_LOCKS: Dict[str, asyncio.Lock] = {}


async def _build_mcp_tools_for_tenant(
    effective_config: EffectiveTenantConfig,
) -> Dict[str, List[Any]]:
    print("[ORCH-LOADER] _build_mcp_tools_for_tenant called")
    server_configs: Dict[str, Dict[str, Any]] = {}
    for agent_cfg in effective_config.agents:
        for binding in agent_cfg.bindings:
            server = binding.mcp_server
            name = server.name
            if name in server_configs:
                continue

            transport = (server.transport or "").strip()
            endpoint = (server.endpoint or "").strip()
            if not endpoint:
                continue

            if transport == "stdio":
                try:
                    parts = shlex.split(endpoint)
                except Exception:
                    parts = [endpoint]
                if not parts:
                    continue
                command = parts[0]
                args = parts[1:]
                server_configs[name] = {
                    "transport": "stdio",
                    "command": command,
                    "args": args,
                }
            elif transport in ("http", "streamable_http"):
                server_configs[name] = {
                    "transport": "streamable_http",
                    "url": endpoint,
                }
            elif transport in ("sse", "server_sent_events"):
                server_configs[name] = {
                    "transport": "sse",
                    "url": endpoint,
                }
            else:
                continue

    if not server_configs:
        print("[ORCH-LOADER] No MCP server configs found; returning empty agent_tools")
        return {}, None

    print(f"[ORCH-LOADER] MCP server configs: {server_configs}")
    print(f"[ORCH-LOADER] Building MultiServerMCPClient with servers={list(server_configs.keys())}")
    client = MultiServerMCPClient(server_configs)
    
    exit_stack = AsyncExitStack()
    try:
        tools = []
        for name in client.connections:
            print(f"[ORCH-LOADER] Connecting to server '{name}'...")
            session = await exit_stack.enter_async_context(client.session(name))
            server_tools = await load_mcp_tools(
                session, 
                server_name=name,
                callbacks=client.callbacks,
                tool_interceptors=client.tool_interceptors
            )
            tools.extend(server_tools)
            print(f"[ORCH-LOADER] Loaded {len(server_tools)} tools from '{name}'")
            
        print(f"[ORCH-LOADER] Total tools loaded: {len(tools)}")
    except Exception as e:
        print(f"[ORCH-LOADER] Error loading tools: {e}")
        await exit_stack.aclose()
        raise e

    tool_by_name: Dict[str, Any] = {}
    for tool in tools:
        name = getattr(tool, "name", None)
        if isinstance(name, str):
            tool_by_name[name] = tool
    print(f"[ORCH-LOADER] tool_by_name keys: {list(tool_by_name.keys())}")

    # Tập tất cả tool có sẵn từ các MCP server cho tenant này
    all_tools: List[Any] = list(tool_by_name.values())

    agent_tools: Dict[str, List[Any]] = {}
    for agent_cfg in effective_config.agents:
        selected: List[Any] = []
        for binding in agent_cfg.bindings:
            raw_ids = list(binding.tool_ids or [])

            # Nếu không chỉ rõ tool_ids cho binding này: mặc định dùng toàn bộ tool
            if not raw_ids:
                for tool in all_tools:
                    if tool not in selected:
                        selected.append(tool)
                continue

            for tool_id in raw_ids:
                tool = tool_by_name.get(tool_id)
                if tool and tool not in selected:
                    selected.append(tool)

        # Nếu sau khi duyệt tất cả binding mà vẫn chưa có tool nào
        # nhưng tenant có ít nhất một tool, fallback dùng toàn bộ tool.
        if not selected and all_tools:
            selected = list(all_tools)

        agent_tools[agent_cfg.agent_type] = selected
        print(
            f"[ORCH-LOADER] agent_type={agent_cfg.agent_type!r} "
            f"assigned {len(selected)} tools"
        )

    return agent_tools, exit_stack


from typing import Any, Dict, List, Optional, TypedDict, Annotated
import operator

# OrchestratorState alias dùng chung ChatState để toàn bộ graph vận hành
# trên một kiểu state đa kênh/multi-tenant thống nhất.
OrchestratorState = ChatState

async def get_or_build_graph(
    cache_key: str,
    effective_config: EffectiveTenantConfig,
    planner_node: PlannerNodeFn,
    route_from_planner: RouteFn,
    agent_node_factory: AgentNodeFactory,
) -> Any:
    print(f"[ORCH-LOADER] get_or_build_graph called, cache_key={cache_key}")
    async with _GRAPH_LOCKS.setdefault(cache_key, asyncio.Lock()):
        cached_data = _GRAPH_CACHE.get(cache_key)
        if cached_data is None:
            print(f"[ORCH-LOADER] Cache miss for {cache_key}, building graph and loading tools...")
            agent_tools, exit_stack = await _build_mcp_tools_for_tenant(effective_config)
            summary = {k: len(v) for k, v in agent_tools.items()}
            print(f"[ORCH-LOADER] agent_tools summary for {cache_key}: {summary}")

            builder = StateGraph(OrchestratorState)

            # Node planner
            builder.add_node("planner", planner_node)

            # Node cho từng agent_type (làm phẳng, không dùng map trung gian).
            vision_tools = agent_tools.get("vision", [])
            vision_node = agent_node_factory("vision", vision_tools)
            builder.add_node("vision_agent", vision_node)

            product_tools = agent_tools.get("product", [])
            product_node = agent_node_factory("product", product_tools)
            builder.add_node("product_agent", product_node)

            service_tools = agent_tools.get("service", [])
            service_node = agent_node_factory("service", service_tools)
            builder.add_node("service_agent", service_node)

            accessory_tools = agent_tools.get("accessory", [])
            accessory_node = agent_node_factory("accessory", accessory_tools)
            builder.add_node("accessory_agent", accessory_node)

            faq_tools = agent_tools.get("faq", [])
            faq_node = agent_node_factory("faq", faq_tools)
            builder.add_node("faq_agent", faq_node)

            knowledge_tools = agent_tools.get("knowledge", [])
            knowledge_node = agent_node_factory("knowledge", knowledge_tools)
            builder.add_node("knowledge_agent", knowledge_node)

            store_info_tools = agent_tools.get("store_info", [])
            store_info_node = agent_node_factory("store_info", store_info_tools)
            builder.add_node("store_info_agent", store_info_node)

            customer_info_tools = agent_tools.get("customer_info", [])
            customer_info_node = agent_node_factory("customer_info", customer_info_tools)
            builder.add_node("customer_info_agent", customer_info_node)

            order_tools = agent_tools.get("order", [])
            order_node = agent_node_factory("order", order_tools)
            builder.add_node("order_agent", order_node)

            escalation_tools = agent_tools.get("escalation", [])
            escalation_node = agent_node_factory("escalation", escalation_tools)
            builder.add_node("escalation_agent", escalation_node)

            closing_tools = agent_tools.get("closing", [])
            closing_node = agent_node_factory("closing", closing_tools)
            builder.add_node("closing_agent", closing_node)

            # Edge từ START tới planner và từ planner tới các agent node (conditional).
            builder.add_edge(START, "planner")
            builder.add_conditional_edges("planner", route_from_planner)

            # Mặc định: sau mỗi agent node thì kết thúc workflow.
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
            _GRAPH_CACHE[cache_key] = {"graph": graph, "exit_stack": exit_stack}
            print(f"[ORCH-LOADER] Graph compiled and cached for {cache_key}")
            return graph
        else:
            print(f"[ORCH-LOADER] Cache hit for {cache_key}, reusing existing graph")
            return cached_data["graph"]


async def invalidate_graph_cache_for_tenant(tenant_id: str) -> None:
    prefix = f"{tenant_id}:"
    keys = [key for key in list(_GRAPH_CACHE.keys()) if key.startswith(prefix)]
    for key in keys:
        data = _GRAPH_CACHE.pop(key, None)
        if data and isinstance(data, dict):
            exit_stack = data.get("exit_stack")
            if exit_stack:
                print(f"[ORCH-LOADER] Closing MCP sessions for {key}")
                try:
                    await exit_stack.aclose()
                except Exception as e:
                    print(f"[ORCH-LOADER] Error closing MCP sessions: {e}")

        _GRAPH_LOCKS.pop(key, None)
