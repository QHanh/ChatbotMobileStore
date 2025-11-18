from typing import Any, Callable, Dict, List

import asyncio
import shlex

from langchain_core.messages import SystemMessage
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_mcp_adapters.client import MultiServerMCPClient

from chat_mcp.models import EffectiveTenantConfig


State = Dict[str, Any]
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
        return {}

    print(f"[ORCH-LOADER] MCP server configs: {server_configs}")
    print(f"[ORCH-LOADER] Building MultiServerMCPClient with servers={list(server_configs.keys())}")
    client = MultiServerMCPClient(server_configs)
    tools = await client.get_tools()
    print(f"[ORCH-LOADER] MultiServerMCPClient.get_tools returned {len(tools)} tools")

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

    return agent_tools


async def get_or_build_graph(
    cache_key: str,
    effective_config: EffectiveTenantConfig,
    agent_node_mapping: Dict[str, str],
    planner_node: PlannerNodeFn,
    route_from_planner: RouteFn,
    agent_node_factory: AgentNodeFactory,
) -> Any:
    print(f"[ORCH-LOADER] get_or_build_graph called, cache_key={cache_key}")
    async with _GRAPH_LOCKS.setdefault(cache_key, asyncio.Lock()):
        graph = _GRAPH_CACHE.get(cache_key)
        if graph is None:
            print(f"[ORCH-LOADER] Cache miss for {cache_key}, building graph and loading tools...")
            agent_tools = await _build_mcp_tools_for_tenant(effective_config)
            summary = {k: len(v) for k, v in agent_tools.items()}
            print(f"[ORCH-LOADER] agent_tools summary for {cache_key}: {summary}")

            builder = StateGraph(dict)

            builder.add_node("planner", planner_node)

            def make_agent_node(agent_type: str, node_name: str) -> None:
                tools_for_agent = agent_tools.get(agent_type, [])
                node_fn = agent_node_factory(agent_type, tools_for_agent)
                builder.add_node(node_name, node_fn)

            for agent_type, node_name in agent_node_mapping.items():
                make_agent_node(agent_type, node_name)

            builder.add_edge(START, "planner")
            builder.add_conditional_edges("planner", route_from_planner)

            for node_name in agent_node_mapping.values():
                builder.add_edge(node_name, END)

            graph = builder.compile()
            _GRAPH_CACHE[cache_key] = graph
            print(f"[ORCH-LOADER] Graph compiled and cached for {cache_key}")
        else:
            print(f"[ORCH-LOADER] Cache hit for {cache_key}, reusing existing graph")

    return graph


def invalidate_graph_cache_for_tenant(tenant_id: str) -> None:
    prefix = f"{tenant_id}:"
    keys = [key for key in list(_GRAPH_CACHE.keys()) if key.startswith(prefix)]
    for key in keys:
        _GRAPH_CACHE.pop(key, None)
        _GRAPH_LOCKS.pop(key, None)
