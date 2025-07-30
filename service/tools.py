from langchain_core.tools import tool
from langchain.tools import StructuredTool
from typing import Optional, List, Dict, Any, Union
from functools import partial

from .search_service import search_products, search_services
from .models.schemas import SearchProductInput, SearchServiceInput, OrderProductInput, OrderServiceInput

def search_products_logic(
    index_name: str,
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các sản phẩm điện thoại có trong kho hàng của cửa hàng.
    Cung cấp các tiêu chí cụ thể như model, màu sắc, dung lượng, tình trạng máy, hoặc khoảng giá để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm sản phẩm cho index: {index_name} ---")
    results = search_products(
        index_name=index_name,
        model=model,
        mau_sac=mau_sac,
        dung_luong=dung_luong,
        tinh_trang_may=tinh_trang_may,
        min_gia=min_gia,
        max_gia=max_gia
    )
    return results

def search_services_logic(
    index_name: str,
    ten_dich_vu: Optional[str] = None,
    ten_san_pham: Optional[str] = None,
    chi_tiet_dich_vu: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các dịch vụ sửa chữa điện thoại có trong dữ liệu của cửa hàng.
    Cung cấp các tiêu chí cụ thể như tên dịch vụ, tên sản phẩm điện thoại được sửa chữa, chi tiết dịch vụ để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm dịch vụ cho index: {index_name} ---")

    results = search_services(
        index_name=index_name,
        ten_dich_vu=ten_dich_vu,
        ten_san_pham=ten_san_pham,
        chi_tiet_dich_vu=chi_tiet_dich_vu
    )
    return results

@tool("create_order_product_tool", args_schema=OrderProductInput)
def create_order_product_tool(
    ma_san_pham: str,
    ten_san_pham: str,
    so_luong: int,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str
) -> Dict[str, Union[str, int]]:
    """
    Sử dụng công cụ này khi người dùng muốn đặt mua một sản phẩm.
    Cần thu thập đủ thông tin: mã sản phẩm (ma_san_pham), tên sản phẩm (ten_san_pham), số lượng, tên khách hàng, số điện thoại và địa chỉ khách hàng.
    Công cụ sẽ xác nhận việc tạo đơn hàng và trả về mã đơn hàng.
    """
    print("--- LangChain Agent đã gọi công cụ tạo đơn hàng sản phẩm ---")
    print(f"Thông tin đơn hàng sản phẩm: Mã SP={ma_san_pham}, Tên SP={ten_san_pham}, Số lượng={so_luong}, Tên KH={ten_khach_hang}, SĐT={so_dien_thoai}, Địa chỉ={dia_chi}")
    
    order_id = f"DH_{so_dien_thoai[-4:]}_{ma_san_pham.split('-')[-1]}"
    order_detail = {
        "order_id": order_id,
        "ma_san_pham": ma_san_pham,
        "ten_san_pham": ten_san_pham,
        "so_luong": so_luong,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
    }

    return {
        "status": "success",
        "message": f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}.",
        "order_detail": order_detail
    }

@tool("create_order_service_tool", args_schema=OrderServiceInput)
def create_order_service_tool(
    ma_dich_vu: str,
    ten_dich_vu: str,
    ten_san_pham: str,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str
) -> Dict[str, Union[str, int]]:
    """
    Sử dụng công cụ này khi người dùng muốn đặt một dịch vụ sửa chữa điện thoại.
    Cần thu thập đủ thông tin: mã dịch vụ (ma_dich_vu), tên dịch vụ (ten_dich_vu), tên sản phẩm điện thoại được sửa chữa (ten_san_pham), tên khách hàng, số điện thoại và địa chỉ khách hàng.
    Công cụ sẽ xác nhận việc tạo đơn hàng và trả về mã đơn hàng.
    """
    print("--- LangChain Agent đã gọi công cụ tạo đơn hàng dịch vụ ---")
    print(f"Thông tin đơn hàng dịch vụ: Mã DV={ma_dich_vu}, Tên DV={ten_dich_vu}, Tên SP={ten_san_pham}, Tên KH={ten_khach_hang}, SĐT={so_dien_thoai}, Địa chỉ={dia_chi}")

    order_id = f"DH_{so_dien_thoai[-4:]}_{ma_dich_vu.split('-')[-1]}"
    order_detail = {
        "order_id": order_id,
        "ma_dich_vu": ma_dich_vu,
        "ten_dich_vu": ten_dich_vu,
        "ten_san_pham": ten_san_pham,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
    }

    return {
        "status": "success",
        "message": f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}.",
        "order_detail": order_detail
    }

@tool
def escalate_to_human_tool() -> str:
    """
    Sử dụng công cụ này khi người dùng yêu cầu được nói chuyện với nhân viên tư vấn, hoặc khi các công cụ khác không thể giải quyết được yêu cầu phức tạp của họ.
    Công cụ này sẽ kết nối người dùng đến một nhân viên thật.
    """
    print("--- Agent đã gọi công cụ chuyển cho người thật ---")
    return "Đang kết nối anh/chị với nhân viên tư vấn. Anh/chị vui lòng chờ trong giây lát..."

@tool
def end_conversation_tool() -> str:
    """
    Sử dụng công cụ này khi người dùng chào tạm biệt, cảm ơn hoặc không có yêu cầu nào khác.
    Công cụ này sẽ kết thúc cuộc trò chuyện một cách lịch sự.
    """
    print("--- Agent đã gọi công cụ kết thúc trò chuyện ---")
    return "Cảm ơn anh/chị đã quan tâm đến cửa hàng của chúng em. Hẹn gặp lại anh/chị lần sau!"


def create_customer_tools(customer_id: str, service_feature_enabled: bool = True) -> list:
    """
    Tạo một danh sách các tool dành riêng cho một khách hàng cụ thể.
    """
    index_name_product = f"product_{customer_id}"  
    customer_search_product_func = partial(search_products_logic, index_name=index_name_product)
    
    search_product_tool = StructuredTool.from_function(
        func=customer_search_product_func,
        name="search_products_tool",
        description=search_products_logic.__doc__,
        args_schema=SearchProductInput
    )
    
    available_tools = [
        search_product_tool,
        create_order_product_tool,
        escalate_to_human_tool,
        end_conversation_tool
    ]

    if service_feature_enabled:
        index_name_service = f"service_{customer_id}"
        customer_search_service_func = partial(search_services_logic, index_name=index_name_service)
        
        search_service_tool = StructuredTool.from_function(
            func=customer_search_service_func,
            name="search_services_tool",
            description=search_services_logic.__doc__,
            args_schema=SearchServiceInput
        )
        
        available_tools.extend([
            search_service_tool,
            create_order_service_tool,
        ])
    return available_tools
