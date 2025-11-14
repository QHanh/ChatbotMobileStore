import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.database import MCPAgentBinding, MCPServer
from mcp.models import AgentBindingOut, EffectiveAgentConfig, EffectiveTenantConfig, MCPServerRef


# Quản lý client MCP và cache cấu hình/binding theo tenant.
class MCPClientManager:
    def __init__(self) -> None:
        # Cache kết nối tới MCP server theo server_id.
        self._connection_cache: Dict[int, Any] = {}
        # Cache danh sách tool của từng MCP server.
        self._tool_list_cache: Dict[int, Any] = {}
        # Cache agent/effective config theo tenant.
        self._agent_cache: Dict[str, Any] = {}

    # Xóa cache agent/effective config của một tenant (dùng khi config_version thay đổi).
    def invalidate_tenant(self, tenant_id: str) -> None:
        self._agent_cache.pop(tenant_id, None)

    # Parse trường tool_ids (JSON string) thành danh sách các tên tool.
    def _parse_tool_ids(self, value: Optional[str]) -> List[str]:
        if not value:
            return []
        try:
            data = json.loads(value)
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:
            pass
        return []

    # Parse trường defaults (JSON string) thành dict tham số mặc định.
    def _parse_defaults(self, value: Optional[str]) -> Dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    # Kết hợp binding + server DB model thành AgentBindingOut (model trả về API).
    def build_binding_out(self, binding: MCPAgentBinding, server: MCPServer) -> AgentBindingOut:
        server_ref = MCPServerRef(
            id=server.id,
            name=server.name,
            transport=server.transport,
            endpoint=server.endpoint,
            health_status=server.health_status,
        )
        return AgentBindingOut(
            id=binding.id,
            tenant_id=binding.tenant_id,
            agent_type=binding.agent_type,
            mcp_server=server_ref,
            tool_ids=self._parse_tool_ids(binding.tool_ids),
            defaults=self._parse_defaults(binding.defaults),
            priority=binding.priority,
            enabled=binding.enabled,
            version=binding.version,
            updated_at=binding.updated_at,
        )

    # Lấy effective config MCP cho tất cả agent của một tenant (gom theo agent_type).
    def get_effective_config_for_tenant(self, db: Session, tenant_id: str) -> EffectiveTenantConfig:
        rows = (
            db.query(MCPAgentBinding, MCPServer)
            .join(MCPServer, MCPAgentBinding.mcp_server_id == MCPServer.id)
            .filter(MCPAgentBinding.tenant_id == tenant_id)
            .filter(MCPAgentBinding.enabled.is_(True))
            .order_by(MCPAgentBinding.agent_type, MCPAgentBinding.priority)
            .all()
        )
        agent_map: Dict[str, List[AgentBindingOut]] = {}
        for binding, server in rows:
            agent_map.setdefault(binding.agent_type, []).append(self.build_binding_out(binding, server))
        agents: List[EffectiveAgentConfig] = []
        for agent_type, bindings in agent_map.items():
            agents.append(EffectiveAgentConfig(agent_type=agent_type, bindings=bindings))
        return EffectiveTenantConfig(tenant_id=tenant_id, agents=agents)

    # Lấy effective config MCP cho một agent_type cụ thể của tenant.
    def get_effective_config_for_agent(self, db: Session, tenant_id: str, agent_type: str) -> EffectiveAgentConfig:
        rows = (
            db.query(MCPAgentBinding, MCPServer)
            .join(MCPServer, MCPAgentBinding.mcp_server_id == MCPServer.id)
            .filter(MCPAgentBinding.tenant_id == tenant_id)
            .filter(MCPAgentBinding.agent_type == agent_type)
            .filter(MCPAgentBinding.enabled.is_(True))
            .order_by(MCPAgentBinding.priority)
            .all()
        )
        bindings: List[AgentBindingOut] = [self.build_binding_out(binding, server) for binding, server in rows]
        return EffectiveAgentConfig(agent_type=agent_type, bindings=bindings)
