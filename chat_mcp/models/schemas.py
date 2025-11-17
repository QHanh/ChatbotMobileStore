from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MCPServerBase(BaseModel):
    name: str = Field(description="Unique name for the MCP server.")
    transport: str = Field(description="Transport type, e.g. 'stdio', 'http', 'sse'.")
    endpoint: Optional[str] = Field(default=None, description="Endpoint URL or command.")
    auth_ref: Optional[str] = Field(default=None, description="Reference to external auth/secret.")
    tags: Optional[str] = Field(default=None, description="Free-form tags for this server.")


class MCPServerCreate(MCPServerBase):
    pass


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    transport: Optional[str] = None
    endpoint: Optional[str] = None
    auth_ref: Optional[str] = None
    tags: Optional[str] = None
    health_status: Optional[str] = None


class MCPServerOut(MCPServerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    health_status: Optional[str] = None
    last_checked: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AgentBindingBase(BaseModel):
    mcp_server_id: int = Field(description="ID of the MCP server this binding uses.")
    tool_ids: Optional[List[str]] = Field(default=None, description="List of MCP tool identifiers.")
    defaults: Optional[Dict[str, Any]] = Field(default=None, description="Default parameters for this binding.")
    priority: int = Field(default=1, description="Lower value means higher priority.")
    enabled: bool = Field(default=True, description="Whether this binding is active.")
    version: Optional[int] = Field(default=None, description="Optional version for the binding.")


class AgentBindingCreate(AgentBindingBase):
    pass


class AgentBindingUpdate(BaseModel):
    mcp_server_id: Optional[int] = None
    tool_ids: Optional[List[str]] = None
    defaults: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    version: Optional[int] = None


class MCPServerRef(BaseModel):
    id: int
    name: str
    transport: str
    endpoint: Optional[str] = None
    health_status: Optional[str] = None


class AgentBindingOut(BaseModel):
    id: int
    tenant_id: str
    agent_type: str
    mcp_server: MCPServerRef
    tool_ids: List[str]
    defaults: Dict[str, Any]
    priority: int
    enabled: bool
    version: Optional[int] = None
    updated_at: datetime


class EffectiveAgentConfig(BaseModel):
    agent_type: str
    bindings: List[AgentBindingOut]


class EffectiveTenantConfig(BaseModel):
    tenant_id: str
    agents: List[EffectiveAgentConfig]


class ProbeResult(BaseModel):
    server: MCPServerOut
    tools: List[str]
