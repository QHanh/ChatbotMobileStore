import json
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.database import MCPServer, MCPAgentBinding, get_db
from mcp.models import MCPServerCreate, MCPServerOut, MCPServerUpdate, ProbeResult

router = APIRouter()


# Tạo mới một MCP server (thêm cấu hình server MCP vào hệ thống).
@router.post("/config/mcp/servers", response_model=MCPServerOut)
async def create_mcp_server(payload: MCPServerCreate, db: Session = Depends(get_db)) -> MCPServerOut:
    server = MCPServer(
        name=payload.name,
        transport=payload.transport,
        endpoint=payload.endpoint,
        auth_ref=payload.auth_ref,
        tags=payload.tags,
        health_status="unknown",
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return server


# Lấy danh sách tất cả MCP servers.
@router.get("/config/mcp/servers", response_model=List[MCPServerOut])
async def list_mcp_servers(db: Session = Depends(get_db)) -> List[MCPServerOut]:
    servers = db.query(MCPServer).order_by(MCPServer.id).all()
    return servers


# Lấy chi tiết một MCP server theo server_id.
@router.get("/config/mcp/servers/{server_id}", response_model=MCPServerOut)
async def get_mcp_server(server_id: int, db: Session = Depends(get_db)) -> MCPServerOut:
    server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    return server


# Cập nhật thông tin một MCP server (transport, endpoint, auth_ref, tags, ...).
@router.patch("/config/mcp/servers/{server_id}", response_model=MCPServerOut)
async def update_mcp_server(server_id: int, payload: MCPServerUpdate, db: Session = Depends(get_db)) -> MCPServerOut:
    server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(server, field, value)
    server.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(server)
    return server


# Xóa một MCP server (nếu chưa bị ràng buộc bởi bất kỳ agent binding nào).
@router.delete("/config/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: int, db: Session = Depends(get_db)) -> dict:
    server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    binding = db.query(MCPAgentBinding).filter(MCPAgentBinding.mcp_server_id == server_id).first()
    if binding:
        raise HTTPException(status_code=400, detail="Cannot delete server while bindings still reference it.")
    db.delete(server)
    db.commit()
    return {"message": "MCP server deleted."}


# Kiểm tra sức khỏe MCP server và (tạm thời) trả về danh sách tool rỗng.
@router.post("/config/mcp/servers/{server_id}/probe", response_model=ProbeResult)
async def probe_mcp_server(server_id: int, db: Session = Depends(get_db)) -> ProbeResult:
    server = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    server.health_status = "unknown"
    server.last_checked = datetime.now(timezone.utc)
    server.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(server)
    tools: List[str] = []
    return ProbeResult(server=server, tools=tools)
