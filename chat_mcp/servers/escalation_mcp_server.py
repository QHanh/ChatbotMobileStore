"""MCP server cho domain escalation (chuyển tiếp cho người thật).

Wrap logic ``escalate_to_human_tool`` hiện tại qua MCP.
"""

from mcp.server.fastmcp import FastMCP
from database.database import SessionLocal
from service.prompts.prompt_service import load_instructions


mcp = FastMCP(name="escalation-mcp")


@mcp.tool()
async def escalation_escalate_to_human() -> str:
    """Trả về thông điệp chuyển cho người thật.

    Đọc nội dung từ bảng SystemInstruction với key
    ``tool.escalate_to_human.response`` giống logic ``escalate_to_human_tool``.
    """

    db = SessionLocal()
    try:
        instr = load_instructions(db)
        return instr.get(
            "tool.escalate_to_human.response",
            "Đang kết nối anh/chị với nhân viên tư vấn. Anh/chị vui lòng chờ trong giây lát...",
        )
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run()
