from langchain_core.tools import tool
from langchain.tools import StructuredTool
from typing import Optional, List, Dict, Any, Union
from functools import partial
import os
from elasticsearch import AsyncElasticsearch

from service.retrieve.search_service import search_products, search_services, search_accessories
from service.retrieve.retrieve_vector_service import retrieve_documents
from service.models.schemas import (
    SearchProductInput, SearchServiceInput, OrderProductInput, 
    OrderServiceInput, SearchAccessoryInput, OrderAccessoryInput,
    RetrieveDocumentInput, SendImageInput
)
from service.integrations.sheet_service import insert_order_to_sheet

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

async def retrieve_document_logic(
    tenant_id: str,
    query: str
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm thông tin chung, chính sách, hướng dẫn hoặc bất kỳ câu hỏi nào không liên quan trực tiếp đến thông số kỹ thuật của một sản phẩm, dịch vụ hoặc phụ kiện cụ thể.
    Ví dụ: "chính sách công ty", "hướng dẫn đổi trả", "địa chỉ cửa hàng".
    Công cụ này sẽ truy xuất thông tin từ cơ sở tri thức, thông tin của cửa hàng.
    """
    print(f"--- Agent đã gọi công cụ truy xuất tài liệu cho tenant: {tenant_id} ---")
    results = await retrieve_documents(query=query, tenant_id=tenant_id)
    return results

async def search_products_logic(
    es_client: AsyncElasticsearch,
    customer_id: str,
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    loai_thiet_bi: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các sản phẩm điện thoại có trong kho hàng của cửa hàng.
    Cung cấp các tiêu chí cụ thể như model, màu sắc, dung lượng, tình trạng máy (trầy xước, xước nhẹ), loại thiết bị (Cũ, Mới), hoặc khoảng giá để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm sản phẩm cho khách hàng: {customer_id} ---")
    results = await search_products(
        es_client=es_client,
        customer_id=customer_id,
        model=model,
        mau_sac=mau_sac,
        dung_luong=dung_luong,
        tinh_trang_may=tinh_trang_may,
        loai_thiet_bi=loai_thiet_bi,
        min_gia=min_gia,
        max_gia=max_gia
    )
    return results

async def search_services_logic(
    es_client: AsyncElasticsearch,
    customer_id: str,
    ten_dich_vu: Optional[str] = None,
    ten_san_pham: Optional[str] = None,
    loai_dich_vu: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các dịch vụ sửa chữa điện thoại có trong dữ liệu của cửa hàng.
    Cung cấp các tiêu chí cụ thể như tên dịch vụ, tên sản phẩm điện thoại được sửa chữa, hãng sản phẩm ví dụ iPhone, màu sắc sản phẩm ví dụ đỏ, hãng dịch vụ ví dụ Pin Lithium để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm dịch vụ cho khách hàng: {customer_id} ---")

    results = await search_services(
        es_client=es_client,
        customer_id=customer_id,
        ten_dich_vu=ten_dich_vu,
        ten_san_pham=ten_san_pham,
        loai_dich_vu=loai_dich_vu,
        min_gia=min_gia,
        max_gia=max_gia
    )
    return results

async def search_accessories_logic(
    es_client: AsyncElasticsearch,
    customer_id: str,
    ten_phu_kien: Optional[str] = None,
    phan_loai_phu_kien: Optional[str] = None,
    thuoc_tinh_phu_kien: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các phụ kiện có trong dữ liệu của cửa hàng.
    Cung cấp các tiêu chí cụ thể như tên phụ kiện, thuộc tính phụ kiện, phân loại phụ kiện, hoặc khoảng giá để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm phụ kiện cho khách hàng: {customer_id} ---")
    results = await search_accessories(
        es_client=es_client,
        customer_id=customer_id,
        ten_phu_kien=ten_phu_kien,
        phan_loai_phu_kien=phan_loai_phu_kien,
        thuoc_tinh_phu_kien=thuoc_tinh_phu_kien,
        min_gia=min_gia,
        max_gia=max_gia
    )
    return results

@tool("create_order_product_tool", args_schema=OrderProductInput)
async def create_order_product_tool(
    ma_san_pham: str,
    ten_san_pham: str,
    so_luong: int,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str
) -> Dict[str, Union[str, int]]:
    """
    Sử dụng công cụ này khi người dùng muốn đặt mua một sản phẩm.
    Cần thu thập đủ thông tin: tên khách hàng, số điện thoại và địa chỉ khách hàng.
    Các thông tin gồm: mã sản phẩm (ma_san_pham), tên sản phẩm (ten_san_pham), số lượng bạn hãy tự phát hiện và cho vào theo yêu cầu của khách hàng và theo dữ liệu tìm kiếm được.
    Công cụ sẽ xác nhận việc tạo đơn hàng và trả về mã đơn hàng.
    """
    print("--- LangChain Agent đã gọi công cụ tạo đơn hàng sản phẩm ---")
    
    order_id = f"DHSP_{so_dien_thoai[-4:]}_{ma_san_pham.split('-')[-1]}"
    order_detail = {
        "order_id": order_id,
        "ma_san_pham": ma_san_pham,
        "ten_san_pham": ten_san_pham,
        "so_luong": so_luong,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
        "dia_chi": dia_chi,
        "loai_don_hang": "Sản phẩm"
    }

    if SPREADSHEET_ID:
        insert_order_to_sheet(
            spreadsheet_id=SPREADSHEET_ID,
            worksheet_name="DonHangSanPham",
            order_data=order_detail
        )
    
    return {
        "status": "success",
        "message": f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}.",
        "order_detail": order_detail
    }

@tool("create_order_service_tool", args_schema=OrderServiceInput)
async def create_order_service_tool(
    ma_dich_vu: str,
    ten_dich_vu: str,
    ten_san_pham: str,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str
) -> Dict[str, Union[str, int]]:
    """
    Sử dụng công cụ này khi người dùng muốn đặt một dịch vụ sửa chữa điện thoại.
    Cần thu thập đủ thông tin: tên khách hàng, số điện thoại và địa chỉ khách hàng.
    Các thông tin gồm mã dịch vụ (ma_dich_vu), tên dịch vụ (ten_dich_vu), tên sản phẩm điện thoại được sửa chữa (ten_san_pham) bạn hãy tự phát hiện và cho vào theo yêu cầu của khách hàng và theo dữ liệu tìm kiếm được.
    Công cụ sẽ xác nhận việc tạo đơn hàng và trả về mã đơn hàng.
    """
    print("--- LangChain Agent đã gọi công cụ tạo đơn hàng dịch vụ ---")

    order_id = f"DHDV_{so_dien_thoai[-4:]}_{ma_dich_vu.split('-')[-1]}"
    order_detail = {
        "order_id": order_id,
        "ma_dich_vu": ma_dich_vu,
        "ten_dich_vu": ten_dich_vu,
        "ten_san_pham_sua_chua": ten_san_pham,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
        "dia_chi": dia_chi,
        "loai_don_hang": "Dịch vụ"
    }

    if SPREADSHEET_ID:
        insert_order_to_sheet(
            spreadsheet_id=SPREADSHEET_ID,
            worksheet_name="DonHangDichVu",
            order_data=order_detail
        )

    return {
        "status": "success",
        "message": f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}.",
        "order_detail": order_detail
    }

@tool("create_order_accessory_tool", args_schema=OrderAccessoryInput)
async def create_order_accessory_tool(
    ma_phu_kien: str,
    ten_phu_kien: str,
    so_luong: int,
    ten_khach_hang: str,
    so_dien_thoai: str,
    dia_chi: str
) -> Dict[str, Union[str, int]]:
    """
    Sử dụng công cụ này khi người dùng muốn đặt mua một phụ kiện.
    Cần thu thập đủ thông tin: tên khách hàng, số điện thoại và địa chỉ khách hàng.
    Các thông tin gồm: mã phụ kiện (ma_phu_kien), tên phụ kiện (ten_phu_kien), số lượng bạn hãy tự phát hiện và cho vào theo yêu cầu của khách hàng và theo dữ liệu tìm kiếm được.
    Công cụ sẽ xác nhận việc tạo đơn hàng và trả về mã đơn hàng.
    """
    print("--- LangChain Agent đã gọi công cụ tạo đơn hàng phụ kiện ---")

    order_id = f"DHPK_{so_dien_thoai[-4:]}_{ma_phu_kien.split('-')[-1]}"
    order_detail = {
        "order_id": order_id,
        "ma_phu_kien": ma_phu_kien,
        "ten_phu_kien": ten_phu_kien,
        "so_luong": so_luong,
        "ten_khach_hang": ten_khach_hang,
        "so_dien_thoai": so_dien_thoai,
        "dia_chi": dia_chi,
        "loai_don_hang": "Phụ kiện"
    }

    if SPREADSHEET_ID:
        insert_order_to_sheet(
            spreadsheet_id=SPREADSHEET_ID,
            worksheet_name="DonHangPhuKien",
            order_data=order_detail
        )
    
    return {
        "status": "success",
        "message": f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}.",
        "order_detail": order_detail
    }

@tool("send_image_tool", args_schema=SendImageInput)
async def send_image_tool(
    image_urls: List[str],
    image_url_holder: List[str]
) -> str:
    """
    Sử dụng công cụ này khi người dùng muốn xem hình ảnh của một sản phẩm, dịch vụ hoặc phụ kiện.
    Công cụ này sẽ chuẩn bị hình ảnh để gửi cho người dùng.
    """
    print(f"--- Agent đã gọi công cụ gửi hình ảnh với các URL: {image_urls} ---")
    
    image_url_holder.extend(image_urls)
    
    return "Hình ảnh đã được chuẩn bị để gửi tới người dùng."

@tool
async def escalate_to_human_tool() -> str:
    """
    Sử dụng công cụ này khi người dùng yêu cầu được nói chuyện với nhân viên tư vấn, hoặc khi các công cụ khác không thể giải quyết được yêu cầu phức tạp của họ.
    Công cụ này sẽ kết nối người dùng đến một nhân viên thật.
    """
    print("--- Agent đã gọi công cụ chuyển cho người thật ---")
    return "Đang kết nối anh/chị với nhân viên tư vấn. Anh/chị vui lòng chờ trong giây lát..."

@tool
async def end_conversation_tool() -> str:
    """
    Sử dụng công cụ này khi người dùng chào tạm biệt, cảm ơn hoặc không có yêu cầu nào khác.
    Công cụ này sẽ kết thúc cuộc trò chuyện một cách lịch sự.
    """
    print("--- Agent đã gọi công cụ kết thúc trò chuyện ---")
    return "Cảm ơn anh/chị đã quan tâm đến cửa hàng của chúng em. Hẹn gặp lại anh/chị lần sau!"


def create_customer_tools(
    es_client: AsyncElasticsearch,
    customer_id: str,
    service_feature_enabled: bool = True, 
    accessory_feature_enabled: bool = True
) -> list:
    """
    Tạo một danh sách các tool dành riêng cho một khách hàng cụ thể.
    """
    customer_search_product_func = partial(search_products_logic, es_client=es_client, customer_id=customer_id)
    
    search_product_tool = StructuredTool.from_function(
        func=customer_search_product_func,
        name="search_products_tool",
        description=search_products_logic.__doc__,
        args_schema=SearchProductInput,
        coroutine=customer_search_product_func
    )

    sanitized_tenant_id = customer_id.replace("-", "_")
    if sanitized_tenant_id and sanitized_tenant_id[0].isdigit():
        sanitized_tenant_id = f"t_{sanitized_tenant_id}"
        
    customer_retrieve_document_func = partial(retrieve_document_logic, tenant_id=sanitized_tenant_id)
    retrieve_document_tool = StructuredTool.from_function(
        func=customer_retrieve_document_func,
        name="retrieve_document_tool",
        description=retrieve_document_logic.__doc__,
        args_schema=RetrieveDocumentInput,
        coroutine=customer_retrieve_document_func
    )

    available_tools = [
        search_product_tool,
        retrieve_document_tool,
        create_order_product_tool,
        escalate_to_human_tool,
        end_conversation_tool
    ]

    if service_feature_enabled:
        customer_search_service_func = partial(search_services_logic, es_client=es_client, customer_id=customer_id)
        
        search_service_tool = StructuredTool.from_function(
            func=customer_search_service_func,
            name="search_services_tool",
            description=search_services_logic.__doc__,
            args_schema=SearchServiceInput,
            coroutine=customer_search_service_func
        )
        
        available_tools.extend([
            search_service_tool,
            create_order_service_tool,
        ])

    if accessory_feature_enabled:
        customer_search_accessory_func = partial(search_accessories_logic, es_client=es_client, customer_id=customer_id)
        
        search_accessory_tool = StructuredTool.from_function(
            func=customer_search_accessory_func,
            name="search_accessories_tool",
            description=search_accessories_logic.__doc__,
            args_schema=SearchAccessoryInput,
            coroutine=customer_search_accessory_func
        )

        available_tools.extend([
            search_accessory_tool,
            create_order_accessory_tool,
        ])

    return available_tools
