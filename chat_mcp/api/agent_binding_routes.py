import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import MCPAgentBinding, MCPServer, Customer, get_db
from chat_mcp.models import (
    AgentBindingCreate,
    AgentBindingOut,
    AgentBindingUpdate,
    EffectiveAgentConfig,
    EffectiveTenantConfig,
)
from chat_mcp.services import MCPClientManager

router = APIRouter()
client_manager = MCPClientManager()


# Hàm tiện ích: lấy thông tin khách hàng theo tenant_id; nếu chưa có thì tạo mới.
def get_or_create_customer(db: Session, tenant_id: str) -> Customer:
    customer = db.query(Customer).filter(Customer.customer_id == tenant_id).first()
    if not customer:
        customer = Customer(customer_id=tenant_id)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    return customer


# Hàm tiện ích: tăng version cấu hình MCP cho tenant, dùng để invalid cache.
def touch_config_version(db: Session, tenant_id: str) -> int:
    customer = get_or_create_customer(db, tenant_id)
    current = customer.config_version or 0
    customer.config_version = current + 1
    db.commit()
    db.refresh(customer)
    return customer.config_version


# Tạo mới binding giữa agent (agent_type) và MCP server cho một tenant.
@router.post("/config/agents/{tenant_id}/{agent_type}/bindings", response_model=AgentBindingOut)
async def create_agent_binding(
    tenant_id: str,
    agent_type: str,
    payload: AgentBindingCreate,
    db: Session = Depends(get_db),
) -> AgentBindingOut:
    server = db.query(MCPServer).filter(MCPServer.id == payload.mcp_server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    tool_ids = json.dumps(payload.tool_ids) if payload.tool_ids is not None else None
    defaults = json.dumps(payload.defaults) if payload.defaults is not None else None
    binding = MCPAgentBinding(
        tenant_id=tenant_id,
        agent_type=agent_type,
        mcp_server_id=payload.mcp_server_id,
        tool_ids=tool_ids,
        defaults=defaults,
        priority=payload.priority,
        enabled=payload.enabled,
        version=payload.version,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    touch_config_version(db, tenant_id)
    return client_manager.build_binding_out(binding, server)


# Lấy danh sách tất cả binding của một agent_type cho một tenant.
@router.get("/config/agents/{tenant_id}/{agent_type}/bindings", response_model=List[AgentBindingOut])
async def list_agent_bindings(tenant_id: str, agent_type: str, db: Session = Depends(get_db)) -> List[AgentBindingOut]:
    rows = (
        db.query(MCPAgentBinding, MCPServer)
        .join(MCPServer, MCPAgentBinding.mcp_server_id == MCPServer.id)
        .filter(MCPAgentBinding.tenant_id == tenant_id)
        .filter(MCPAgentBinding.agent_type == agent_type)
        .order_by(MCPAgentBinding.priority)
        .all()
    )
    return [client_manager.build_binding_out(binding, server) for binding, server in rows]


# Cập nhật thông tin một binding cụ thể (tool_ids, defaults, priority, enabled, ...).
@router.patch("/config/agents/{tenant_id}/{agent_type}/bindings/{binding_id}", response_model=AgentBindingOut)
async def update_agent_binding(
    tenant_id: str,
    agent_type: str,
    binding_id: int,
    payload: AgentBindingUpdate,
    db: Session = Depends(get_db),
) -> AgentBindingOut:
    binding = (
        db.query(MCPAgentBinding)
        .filter(MCPAgentBinding.id == binding_id)
        .filter(MCPAgentBinding.tenant_id == tenant_id)
        .filter(MCPAgentBinding.agent_type == agent_type)
        .first()
    )
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found.")
    data = payload.dict(exclude_unset=True)
    if "tool_ids" in data:
        value = data.pop("tool_ids")
        binding.tool_ids = json.dumps(value) if value is not None else None
    if "defaults" in data:
        value = data.pop("defaults")
        binding.defaults = json.dumps(value) if value is not None else None
    for field, value in data.items():
        setattr(binding, field, value)
    binding.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(binding)
    server = db.query(MCPServer).filter(MCPServer.id == binding.mcp_server_id).first()
    touch_config_version(db, tenant_id)
    return client_manager.build_binding_out(binding, server)


# Xóa một binding, đồng thời tăng version config và xóa cache tenant tương ứng.
@router.delete("/config/agents/{tenant_id}/{agent_type}/bindings/{binding_id}")
async def delete_agent_binding(
    tenant_id: str,
    agent_type: str,
    binding_id: int,
    db: Session = Depends(get_db),
) -> dict:
    binding = (
        db.query(MCPAgentBinding)
        .filter(MCPAgentBinding.id == binding_id)
        .filter(MCPAgentBinding.tenant_id == tenant_id)
        .filter(MCPAgentBinding.agent_type == agent_type)
        .first()
    )
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found.")
    db.delete(binding)
    db.commit()
    touch_config_version(db, tenant_id)
    client_manager.invalidate_tenant(tenant_id)
    return {"message": "Binding deleted."}


# Lấy cấu hình MCP hiệu lực cho tất cả agent của một tenant.
@router.get("/config/agents/{tenant_id}/effective", response_model=EffectiveTenantConfig)
async def get_effective_config_for_tenant(tenant_id: str, db: Session = Depends(get_db)) -> EffectiveTenantConfig:
    return client_manager.get_effective_config_for_tenant(db, tenant_id)


# Lấy cấu hình MCP hiệu lực cho một agent_type cụ thể của tenant.
@router.get("/config/agents/{tenant_id}/{agent_type}/effective", response_model=EffectiveAgentConfig)
async def get_effective_config_for_agent(
    tenant_id: str,
    agent_type: str,
    db: Session = Depends(get_db),
) -> EffectiveAgentConfig:
    return client_manager.get_effective_config_for_agent(db, tenant_id, agent_type)


# Tăng version cấu hình và xóa cache agent của tenant để reload cấu hình MCP.
@router.post("/config/agents/{tenant_id}/reload")
async def reload_agent_config(tenant_id: str, db: Session = Depends(get_db)) -> dict:
    version = touch_config_version(db, tenant_id)
    client_manager.invalidate_tenant(tenant_id)
    return {"tenant_id": tenant_id, "config_version": version}
