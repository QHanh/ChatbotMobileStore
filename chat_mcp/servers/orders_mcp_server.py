"""MCP server cho domain tạo đơn hàng (orders).

Wrap logic ``create_order_*_tool_with_db`` hiện tại qua MCP.
"""

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from service.utils.tools import (
    create_order_product_tool_with_db,
    create_order_service_tool_with_db,
    create_order_accessory_tool_with_db,
)


mcp = FastMCP(name="orders-mcp")


@mcp.tool()
async def orders_create_product(
    customer_id: str,
    thread_id: str,
    ma_san_pham: str,
    ten_san_pham: str,
    so_luong: int,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str,
) -> Dict[str, Any]:
    """Tạo đơn hàng sản phẩm (wrap create_order_product_tool_with_db).

    MCP chỉ là lớp mỏng gọi lại StructuredTool đã có để giữ nguyên logic DB + Zalo.
    """

    tool = create_order_product_tool_with_db(customer_id=customer_id, thread_id=thread_id)
    payload = {
        "ma_san_pham": ma_san_pham,
        "ten_san_pham": ten_san_pham,
        "so_luong": so_luong,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
        "dia_chi": dia_chi,
    }
    # StructuredTool.invoke là hàm sync, nhưng bên trong đã tự xử lý DB.
    return tool.invoke(payload)


@mcp.tool()
async def orders_create_service(
    customer_id: str,
    thread_id: str,
    ma_dich_vu: str,
    ten_dich_vu: str,
    ten_san_pham: str,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str,
    loai_dich_vu: str | None = None,
) -> Dict[str, Any]:
    """Tạo đơn hàng dịch vụ sửa chữa (wrap create_order_service_tool_with_db)."""

    tool = create_order_service_tool_with_db(customer_id=customer_id, thread_id=thread_id)
    payload = {
        "ma_dich_vu": ma_dich_vu,
        "ten_dich_vu": ten_dich_vu,
        "loai_dich_vu": loai_dich_vu,
        "ten_san_pham": ten_san_pham,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
        "dia_chi": dia_chi,
    }
    return tool.invoke(payload)


@mcp.tool()
async def orders_create_accessory(
    customer_id: str,
    thread_id: str,
    ma_phu_kien: str,
    ten_phu_kien: str,
    so_luong: int,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str,
) -> Dict[str, Any]:
    """Tạo đơn hàng phụ kiện (wrap create_order_accessory_tool_with_db)."""

    tool = create_order_accessory_tool_with_db(customer_id=customer_id, thread_id=thread_id)
    payload = {
        "ma_phu_kien": ma_phu_kien,
        "ten_phu_kien": ten_phu_kien,
        "so_luong": so_luong,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
        "dia_chi": dia_chi,
    }
    return tool.invoke(payload)


if __name__ == "__main__":
    mcp.run()
