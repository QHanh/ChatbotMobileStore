import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database.database import MCPAgentBinding, MCPServer
from chat_mcp.models import AgentBindingOut, EffectiveAgentConfig, EffectiveTenantConfig, MCPServerRef


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

    def _load_default_servers_from_filesystem(self) -> List[MCPServerRef]:
        """Fallback: load MCP server definitions from chat_mcp/servers package.

        Khi DB chưa có bất kỳ MCPServer nào, ta duyệt thư mục ``chat_mcp/servers``
        và tạo MCPServerRef tạm thời cho mỗi file *_mcp_server.py.
        """

        base_dir = os.path.dirname(os.path.dirname(__file__))
        servers_dir = os.path.join(base_dir, "servers")

        if not os.path.isdir(servers_dir):
            return []

        server_refs: List[MCPServerRef] = []
        next_id = 1

        for entry in sorted(os.listdir(servers_dir)):
            if not entry.endswith("_mcp_server.py"):
                continue
            if entry == "__init__.py":
                continue

            module_name = entry[:-3]  # strip .py
            server_name = module_name
            endpoint = f"python -m chat_mcp.servers.{module_name}"

            server_refs.append(
                MCPServerRef(
                    id=next_id,
                    name=server_name,
                    transport="stdio",
                    endpoint=endpoint,
                    health_status="unknown",
                )
            )
            next_id += 1

        return server_refs

    # Lấy effective config MCP cho tất cả agent của một tenant (gom theo agent_type).
    # Nếu tenant chưa có bản ghi binding nào, mặc định sử dụng TẤT CẢ MCP server
    # cho TẤT CẢ agent_type chuẩn.
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

        # Trường hợp đã cấu hình binding explicit: dùng đúng cấu hình đó.
        if agent_map:
            for agent_type, bindings in agent_map.items():
                agents.append(EffectiveAgentConfig(agent_type=agent_type, bindings=bindings))
            return EffectiveTenantConfig(tenant_id=tenant_id, agents=agents)

        # Fallback: chưa có binding nào cho tenant này.
        # B1: Nếu có MCPServer trong DB, dùng tất cả server cho tất cả agent_type chuẩn.
        servers = db.query(MCPServer).order_by(MCPServer.id).all()
        if servers:
            default_agent_types: List[str] = [
                "vision",
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

            for agent_type in default_agent_types:
                bindings: List[AgentBindingOut] = []
                for server in servers:
                    server_ref = MCPServerRef(
                        id=server.id,
                        name=server.name,
                        transport=server.transport,
                        endpoint=server.endpoint,
                        health_status=server.health_status,
                    )
                    binding_out = AgentBindingOut(
                        id=server.id,
                        tenant_id=tenant_id,
                        agent_type=agent_type,
                        mcp_server=server_ref,
                        tool_ids=[],
                        defaults={},
                        priority=1,
                        enabled=True,
                        version=None,
                        updated_at=server.updated_at or datetime.now(timezone.utc),
                    )
                    bindings.append(binding_out)
                agents.append(EffectiveAgentConfig(agent_type=agent_type, bindings=bindings))

            return EffectiveTenantConfig(tenant_id=tenant_id, agents=agents)

        # B2: Nếu DB cũng chưa có MCPServer nào, fallback cuối cùng:
        # tạo server ảo từ các file trong chat_mcp/servers và gán cho tất cả tenant.
        default_servers = self._load_default_servers_from_filesystem()
        if not default_servers:
            return EffectiveTenantConfig(tenant_id=tenant_id, agents=[])

        # Mapping default tool_ids theo agent_type & tên server (từ các file *_mcp_server.py trong chat_mcp/servers).
        # Điều này bám theo thiết kế trong docs: mỗi agent chỉ dùng một số MCP tools cụ thể.
        default_tool_ids_map: Dict[str, Dict[str, List[str]]] = {
            # Vision Agent: chỉ dùng MCP vision để nhận diện sản phẩm từ ảnh.
            "vision": {
                "vision_mcp_server": ["vision_identify_product"],
            },
            # Product Agent: tìm kiếm sản phẩm.
            "product": {
                "products_mcp_server": ["products_search"],
            },
            # Service Agent: tìm kiếm dịch vụ sửa chữa.
            "service": {
                "services_mcp_server": ["services_search"],
            },
            # Accessory Agent: tìm kiếm phụ kiện/linh kiện.
            "accessory": {
                "accessories_mcp_server": ["accessories_search"],
            },
            # FAQ Agent: tìm kiếm FAQ.
            "faq": {
                "faq_mcp_server": ["faq_search"],
            },
            # Knowledge Agent (GraphRAG): truy vấn kiến thức sâu.
            "knowledge": {
                "knowledge_mcp_server": ["knowledge_graphrag"],
            },
            # Order Agent: tạo đơn hàng sản phẩm/dịch vụ/phụ kiện.
            "order": {
                "orders_mcp_server": [
                    "orders_create_product",
                    "orders_create_service",
                    "orders_create_accessory",
                ],
            },
            # Escalation Agent: chuyển cho người thật.
            "escalation": {
                "escalation_mcp_server": ["escalation_escalate_to_human"],
            },
            # store_info, customer_info, closing: hiện tại dùng tool local → không bind MCP mặc định.
        }

        binding_id = 1
        now = datetime.now(timezone.utc)

        for agent_type, per_server in default_tool_ids_map.items():
            bindings: List[AgentBindingOut] = []
            for server_ref in default_servers:
                tool_ids = per_server.get(server_ref.name)
                if not tool_ids:
                    continue
                binding_out = AgentBindingOut(
                    id=binding_id,
                    tenant_id=tenant_id,
                    agent_type=agent_type,
                    mcp_server=server_ref,
                    tool_ids=tool_ids,
                    defaults={},
                    priority=1,
                    enabled=True,
                    version=None,
                    updated_at=now,
                )
                binding_id += 1
                bindings.append(binding_out)
            if bindings:
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
