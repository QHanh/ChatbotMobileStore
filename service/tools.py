from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union

# Import hàm tìm kiếm logic từ search_service
from .search_service import search_iphones
from .models.schemas import SearchInput, OrderInput

# --- ĐỊNH NGHĨA TOOL TÌM KIẾM SẢN PHẨM ---
@tool("search_iphones_tool", args_schema=SearchInput)
def search_iphones_tool(
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các sản phẩm điện thoại iPhone có trong kho hàng của cửa hàng.
    Cung cấp các tiêu chí cụ thể như model, màu sắc, dung lượng, tình trạng máy, hoặc khoảng giá để lọc kết quả.
    Công cụ sẽ trả về danh sách các sản phẩm phù hợp với thông tin chi tiết.
    """
    print("--- LangChain Agent đã gọi công cụ tìm kiếm iPhone ---")
    print(f"Tham số: model={model}, màu={mau_sac}, dung lượng={dung_luong}, tình trạng={tinh_trang_may}, giá từ={min_gia}, giá đến={max_gia}")
    
    # Gọi hàm logic tìm kiếm từ search_service
    results = search_iphones(
        model=model,
        mau_sac=mau_sac,
        dung_luong=dung_luong,
        tinh_trang_may=tinh_trang_may,
        min_gia=min_gia,
        max_gia=max_gia
    )
    return results

@tool("create_order_tool", args_schema=OrderInput)
def create_order_tool(
    ma_san_pham: str,
    so_luong: int,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str
) -> Dict[str, Union[str, int]]:
    """
    Sử dụng công cụ này khi người dùng muốn đặt mua một sản phẩm.
    Cần thu thập đủ thông tin: mã sản phẩm (ma_san_pham), số lượng, tên khách hàng, số điện thoại và địa chỉ giao hàng.
    Công cụ sẽ xác nhận việc tạo đơn hàng và trả về mã đơn hàng.
    """
    print("--- LangChain Agent đã gọi công cụ tạo đơn hàng ---")
    print(f"Thông tin đơn hàng: Mã SP={ma_san_pham}, Số lượng={so_luong}, Tên KH={ten_khach_hang}, SĐT={so_dien_thoai}, Địa chỉ={dia_chi}")
    
    # --- Logic giả lập tạo đơn hàng ---
    # Trong thực tế, bạn sẽ gọi API hoặc lưu vào database ở đây.
    order_id = f"DH_{so_dien_thoai[-4:]}_{ma_san_pham.split('-')[-1]}"
    
    return {
        "status": "success",
        "message": f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}.",
        "order_id": order_id
    }

@tool
def escalate_to_human_tool() -> str:
    """
    Sử dụng công cụ này khi người dùng yêu cầu được nói chuyện với nhân viên tư vấn, hoặc khi các công cụ khác không thể giải quyết được yêu cầu phức tạp của họ.
    Công cụ này sẽ kết nối người dùng đến một nhân viên thật.
    """
    print("--- LangChain Agent đã gọi công cụ chuyển cho người thật ---")
    return "Đang kết nối bạn với nhân viên tư vấn. Vui lòng chờ trong giây lát..."

@tool
def end_conversation_tool() -> str:
    """
    Sử dụng công cụ này khi người dùng chào tạm biệt, cảm ơn hoặc không có yêu cầu nào khác.
    Công cụ này sẽ kết thúc cuộc trò chuyện một cách lịch sự.
    """
    print("--- LangChain Agent đã gọi công cụ kết thúc trò chuyện ---")
    return "Cảm ơn bạn đã quan tâm đến sản phẩm của cửa hàng. Hẹn gặp lại bạn lần sau!"

# Danh sách các tool có sẵn để agent sử dụng
available_tools = [
    search_iphones_tool,
    create_order_tool,
    escalate_to_human_tool,
    end_conversation_tool
]
