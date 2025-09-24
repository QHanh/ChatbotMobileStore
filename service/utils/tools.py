from langchain_core.tools import tool
import json
import re
import requests
from typing import List, Optional, Dict, Any
from functools import partial
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from service.retrieve.search_service import search_products, search_accessories, search_services
from database.database import get_db
from sqlalchemy.orm import Session
from datetime import datetime
from elasticsearch import AsyncElasticsearch
from service.retrieve.retrieve_vector_service import retrieve_documents
from service.models.schemas import (
    SearchProductInput, SearchServiceInput, SearchAccessoryInput,
    RetrieveDocumentInput, 
    OrderProductInput, 
    OrderServiceInput, 
    OrderAccessoryInput
)
from pydantic import BaseModel, Field
from langchain_core.language_models.base import BaseLanguageModel
from database.database import get_db, ProductOrder, ServiceOrder, AccessoryOrder, StoreInfo

# Schema for checking existing customer info
class CheckCustomerInfoInput(BaseModel):
    """Schema for checking existing customer information"""
    pass  # No input needed as customer_id and thread_id are bound

# Schema for getting store info
class GetStoreInfoInput(BaseModel):
    """Schema for getting store information"""
    pass  # No input needed as customer_id is bound

def validate_thread_id(thread_id: str) -> bool:
    """
    Validate thread_id: must be all digits and at least 9 characters long
    """
    return thread_id.isdigit() and len(thread_id) >= 9

def call_zalo_api(customer_id: str, thread_id: str, customer_name: str, phone: str, address: str, product_name: str) -> dict:
    """
    Call Zalo API to create group with order information
    """
    try:
        url = "https://zaloapi.doiquanai.vn/api/groups/managers"
        
        # Create name with customer info and product
        group_name = f"{customer_name} {phone} {address} {product_name}"
        
        payload = {
            "session_key": customer_id,
            "members": thread_id,
            "name": group_name
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            return {
                "status": "success",
                "message": "Đã tạo nhóm Zalo thành công",
                "data": response.json()
            }
        else:
            return {
                "status": "error",
                "message": f"Lỗi API Zalo: {response.status_code} - {response.text}"
            }
            
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Timeout khi gọi API Zalo"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Lỗi khi gọi API Zalo: {str(e)}"
        }

def create_check_customer_info_tool(customer_id: str, thread_id: str):
    def check_existing_customer_info():
        """
        Kiểm tra xem khách hàng đã có đơn hàng nào trong thread này chưa để lấy thông tin cá nhân.
        
        Sử dụng công cụ này TRƯỚC KHI tạo đơn hàng để:
        1. Kiểm tra xem khách hàng đã có đơn hàng nào trong cuộc trò chuyện này chưa
        2. Nếu có, lấy thông tin cá nhân từ đơn hàng gần nhất
        3. Đưa thông tin cho khách hàng xem và hỏi có muốn thay đổi không
        4. Nếu không có đơn hàng nào, yêu cầu khách hàng cung cấp đầy đủ thông tin cá nhân
        """
        print("--- Agent đã gọi công cụ kiểm tra thông tin khách hàng ---")
        
        db = next(get_db())
        try:
            # Tìm đơn hàng gần nhất của customer trong thread này
            existing_product_order = db.query(ProductOrder).filter(
                ProductOrder.customer_id == customer_id,
                ProductOrder.thread_id == thread_id
            ).order_by(ProductOrder.created_at.desc()).first()
            
            existing_service_order = db.query(ServiceOrder).filter(
                ServiceOrder.customer_id == customer_id,
                ServiceOrder.thread_id == thread_id
            ).order_by(ServiceOrder.created_at.desc()).first()
            
            existing_accessory_order = db.query(AccessoryOrder).filter(
                AccessoryOrder.customer_id == customer_id,
                AccessoryOrder.thread_id == thread_id
            ).order_by(AccessoryOrder.created_at.desc()).first()
            
            # Tìm đơn hàng gần nhất trong tất cả các loại
            all_orders = []
            if existing_product_order:
                all_orders.append(existing_product_order)
            if existing_service_order:
                all_orders.append(existing_service_order)
            if existing_accessory_order:
                all_orders.append(existing_accessory_order)
            
            if not all_orders:
                return {
                    "status": "no_existing_info",
                    "message": "Không tìm thấy đơn hàng nào trong cuộc trò chuyện này. Vui lòng cung cấp đầy đủ thông tin cá nhân: tên, số điện thoại và địa chỉ."
                }
            
            # Lấy đơn hàng gần nhất
            latest_order = max(all_orders, key=lambda x: x.created_at)
            
            existing_info = {
                "ten_khach_hang": latest_order.ten_khach_hang,
                "so_dien_thoai": latest_order.so_dien_thoai,
                "dia_chi": latest_order.dia_chi
            }
            
            return {
                "status": "found_existing_info",
                "message": f"Tôi thấy anh/chị đã có thông tin từ đơn hàng trước trong cuộc trò chuyện này:\n"
                         f"- Tên: {existing_info['ten_khach_hang']}\n"
                         f"- Số điện thoại: {existing_info['so_dien_thoai']}\n"
                         f"- Địa chỉ: {existing_info['dia_chi']}\n\n"
                         f"Anh/chị có muốn sử dụng thông tin này không? Nếu có thay đổi gì, vui lòng cho tôi biết.",
                "existing_info": existing_info
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi khi kiểm tra thông tin khách hàng: {str(e)}"
            }
        finally:
            db.close()
    
    return StructuredTool.from_function(
        func=check_existing_customer_info,
        name="check_customer_info_tool",
        description="Kiểm tra thông tin khách hàng từ đơn hàng trước đó trong thread này",
        args_schema=CheckCustomerInfoInput
    )

def create_get_store_info_tool(customer_id: str):
    def get_store_info():
        """
        Lấy thông tin cửa hàng bao gồm tên, địa chỉ, số điện thoại, email, website, Facebook, bản đồ và hình ảnh.
        
        Sử dụng công cụ này khi khách hàng hỏi về:
        - Địa chỉ cửa hàng
        - Thông tin liên hệ của cửa hàng
        - Số điện thoại cửa hàng
        - Email cửa hàng
        - Website hoặc Facebook của cửa hàng
        - Vị trí cửa hàng trên bản đồ
        - Hình ảnh cửa hàng
        """
        print("--- Agent đã gọi công cụ lấy thông tin cửa hàng ---")
        
        db = next(get_db())
        try:
            store_info = db.query(StoreInfo).filter(StoreInfo.customer_id == customer_id).first()
            
            if not store_info:
                return {
                    "status": "no_info",
                    "message": "Chưa có thông tin cửa hàng được cấu hình. Vui lòng liên hệ quản trị viên để cập nhật thông tin."
                }
            
            # Tạo thông tin cửa hàng để trả về
            store_data = {}
            info_parts = []
            
            if store_info.store_name:
                store_data["ten_cua_hang"] = store_info.store_name
                info_parts.append(f"🏪 **Tên cửa hàng**: {store_info.store_name}")
            
            if store_info.store_address:
                store_data["dia_chi"] = store_info.store_address
                info_parts.append(f"📍 **Địa chỉ**: {store_info.store_address}")
            
            if store_info.store_phone:
                store_data["so_dien_thoai"] = store_info.store_phone
                info_parts.append(f"📞 **Số điện thoại**: {store_info.store_phone}")
            
            if store_info.store_email:
                store_data["email"] = store_info.store_email
                info_parts.append(f"📧 **Email**: {store_info.store_email}")
            
            if store_info.store_website:
                store_data["website"] = store_info.store_website
                info_parts.append(f"🌐 **Website**: {store_info.store_website}")
            
            if store_info.store_facebook:
                store_data["facebook"] = store_info.store_facebook
                info_parts.append(f"📘 **Facebook**: {store_info.store_facebook}")
            
            if store_info.store_address_map:
                store_data["ban_do"] = store_info.store_address_map
                info_parts.append(f"🗺️ **Bản đồ**: {store_info.store_address_map}")
            
            if store_info.store_image:
                store_data["hinh_anh"] = store_info.store_image
                info_parts.append(f"🖼️ **Hình ảnh cửa hàng**: {store_info.store_image}")
            
            if not info_parts:
                return {
                    "status": "empty_info",
                    "message": "Thông tin cửa hàng chưa được cập nhật đầy đủ. Vui lòng liên hệ quản trị viên."
                }
            
            formatted_message = "**THÔNG TIN CỬA HÀNG**\n\n" + "\n\n".join(info_parts)
            
            return {
                "status": "success",
                "message": formatted_message,
                "store_info": store_data
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Lỗi khi lấy thông tin cửa hàng: {str(e)}"
            }
        finally:
            db.close()
    
    return StructuredTool.from_function(
        func=get_store_info,
        name="get_store_info_tool",
        description="Lấy thông tin cửa hàng bao gồm địa chỉ, số điện thoại, email, website, Facebook",
        args_schema=GetStoreInfoInput
    )

async def retrieve_document_logic(
    tenant_id: str,
    query: str
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm thông tin chung, chính sách, hướng dẫn hoặc bất kỳ câu hỏi nào không liên quan trực tiếp đến thông số kỹ thuật của một sản phẩm, dịch vụ hoặc phụ kiện cụ thể.
    Ví dụ: "chính sách công ty", "hướng dẫn đổi trả", "địa chỉ cửa hàng".
    Công cụ này sẽ truy xuất thông tin từ cơ sở tri thức, thông tin của cửa hàng.
    """
    print(f"\n--- Agent đã gọi công cụ truy xuất tài liệu cho tenant: {tenant_id} ---")
    results = await retrieve_documents(query=query, customer_id=tenant_id)
    return results

async def search_products_logic(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: Optional[str] = None,
    model: Optional[str] = None,
    mau_sac: Optional[str] = None,
    dung_luong: Optional[str] = None,
    tinh_trang_may: Optional[str] = None,
    loai_thiet_bi: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    offset: Optional[int] = 0,
    original_query: Optional[str] = None,
    llm: Optional[BaseLanguageModel] = None,
    chat_history: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các sản phẩm điện thoại có trong kho hàng của cửa hàng.
    Cung cấp các tiêu chí cụ thể như model, màu sắc, dung lượng, tình trạng máy (trầy xước, xước nhẹ), loại thiết bị (Cũ, Mới), hoặc khoảng giá để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm sản phẩm cho khách hàng: {customer_id} ---")
    results = await search_products(
        es_client=es_client,
        customer_id=customer_id,
        thread_id=thread_id,
        model=model,
        mau_sac=mau_sac,
        dung_luong=dung_luong,
        tinh_trang_may=tinh_trang_may,
        loai_thiet_bi=loai_thiet_bi,
        min_gia=min_gia,
        max_gia=max_gia,
        offset=offset,
        original_query=original_query,
        llm=llm,
        chat_history=chat_history
    )
    return results

async def search_services_logic(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: Optional[str] = None,
    ten_dich_vu: Optional[str] = None,
    ten_san_pham: Optional[str] = None,
    loai_dich_vu: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    offset: Optional[int] = 0,
    original_query: Optional[str] = None,
    llm: Optional[BaseLanguageModel] = None,
    chat_history: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các dịch vụ sửa chữa điện thoại có trong dữ liệu của cửa hàng.
    Cung cấp các tiêu chí cụ thể như tên dịch vụ, tên sản phẩm điện thoại được sửa chữa (cần thiết), hãng sản phẩm ví dụ iPhone, màu sắc sản phẩm ví dụ đỏ, hãng dịch vụ ví dụ Pin Lithium để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm dịch vụ cho khách hàng: {customer_id} ---")

    results = await search_services(
        es_client=es_client,
        customer_id=customer_id,
        thread_id=thread_id,
        ten_dich_vu=ten_dich_vu,
        ten_san_pham=ten_san_pham,
        loai_dich_vu=loai_dich_vu,
        min_gia=min_gia,
        max_gia=max_gia,
        offset=offset,
        original_query=original_query,
        llm=llm,
        chat_history=chat_history
    )
    return results

async def search_accessories_logic(
    es_client: AsyncElasticsearch,
    customer_id: str,
    thread_id: Optional[str] = None,
    ten_phu_kien: Optional[str] = None,
    phan_loai_phu_kien: Optional[str] = None,
    thuoc_tinh_phu_kien: Optional[str] = None,
    min_gia: Optional[float] = None,
    max_gia: Optional[float] = None,
    offset: Optional[int] = 0,
    original_query: Optional[str] = None,
    llm: Optional[BaseLanguageModel] = None,
    chat_history: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Sử dụng công cụ này để tìm kiếm và tra cứu thông tin các phụ kiện có trong dữ liệu của cửa hàng.
    Cung cấp các tiêu chí cụ thể như tên phụ kiện, thuộc tính phụ kiện, phân loại phụ kiện, hoặc khoảng giá để lọc kết quả.
    """
    print(f"--- Agent đã gọi công cụ tìm kiếm phụ kiện cho khách hàng: {customer_id} ---")
    results = await search_accessories(
        es_client=es_client,
        customer_id=customer_id,
        thread_id=thread_id,
        ten_phu_kien=ten_phu_kien,
        phan_loai_phu_kien=phan_loai_phu_kien,
        thuoc_tinh_phu_kien=thuoc_tinh_phu_kien,
        min_gia=min_gia,
        max_gia=max_gia,
        offset=offset,
        original_query=original_query,
        llm=llm,
        chat_history=chat_history
    )
    return results

def create_order_product_tool_with_db(customer_id: str, thread_id: str):
    def create_order_product(
        ma_san_pham: str = Field(description="Mã sản phẩm"),
        ten_san_pham: str = Field(description="Tên sản phẩm"),
        so_luong: int = Field(description="Số lượng sản phẩm"),
        ten_khach_hang: str = Field(description="Tên khách hàng"),
        so_dien_thoai: str = Field(description="Số điện thoại khách hàng"),
        dia_chi: str = Field(description="Địa chỉ giao hàng")
    ) -> dict:
        """
        Sử dụng công cụ này KHI VÀ CHỈ KHI khách hàng đã xác nhận chốt đơn mua một sản phẩm điện thoại.

        QUAN TRỌNG:
        1.  Tham số `ma_san_pham` và `ten_san_pham` BẮT BUỘC phải được lấy từ kết quả của công cụ `search_products_tool` đã được gọi trước đó trong cuộc trò chuyện và là sản phẩm khách hàng chốt.
        2.  TUYỆT ĐỐI KHÔNG được hỏi khách hàng mã sản phẩm. Luôn tự động lấy nó từ lịch sử tra cứu.
        3.  Trước khi gọi công cụ này, BẮT BUỘC phải hỏi và thu thập đủ thông tin cá nhân của khách hàng, bao gồm: `ten_khach_hang`, `so_dien_thoai`, và `dia_chi`.
        """
        print("--- LangChain Agent đã gọi công cụ tạo đơn hàng sản phẩm ---")

        import time
        timestamp = str(int(time.time()))[-6:]  # Lấy 6 chữ số cuối của timestamp
        order_id = f"DHSP_{so_dien_thoai[-4:]}_{ma_san_pham.split('-')[-1]}_{timestamp}"
        
        # Lưu vào database
        db = next(get_db())
        try:
            new_order = ProductOrder(
                order_id=order_id,
                customer_id=customer_id,
                thread_id=thread_id,
                ma_san_pham=ma_san_pham,
                ten_san_pham=ten_san_pham,
                so_luong=so_luong,
                ten_khach_hang=ten_khach_hang,
                so_dien_thoai=so_dien_thoai,
                dia_chi=dia_chi,
                loai_don_hang="Sản phẩm"
            )
            db.add(new_order)
            db.commit()
            
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
            
            # Call Zalo API only if thread_id is valid
            zalo_result = None
            if validate_thread_id(thread_id):
                zalo_result = call_zalo_api(customer_id, thread_id, ten_khach_hang, so_dien_thoai, dia_chi, ten_san_pham)
            
            success_message = f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}."
            if zalo_result and zalo_result["status"] == "success":
                success_message += " Đã tạo nhóm Zalo để theo dõi đơn hàng."
            elif zalo_result:
                success_message += f" Lưu ý: {zalo_result['message']}"
            
            return {
                "status": "success",
                "message": success_message,
                "order_detail": order_detail,
                # "zalo_result": zalo_result
            }
        except Exception as e:
            db.rollback()
            return {
                "status": "error",
                "message": f"Lỗi khi tạo đơn hàng: {str(e)}"
            }
        finally:
            db.close()
    
    return StructuredTool.from_function(
        func=create_order_product,
        name="create_order_product_tool",
        description="Tạo đơn hàng sản phẩm điện thoại",
        args_schema=OrderProductInput
    )

def create_order_service_tool_with_db(customer_id: str, thread_id: str):
    def create_order_service(
        ma_dich_vu: str = Field(description="Mã dịch vụ"),
        ten_dich_vu: str = Field(description="Tên dịch vụ"),
        loai_dich_vu: Optional[str] = Field(description="Loại dịch vụ"),
        ten_san_pham: str = Field(description="Tên sản phẩm cần sửa chữa"),
        ten_khach_hang: str = Field(description="Tên khách hàng"),
        so_dien_thoai: str = Field(description="Số điện thoại khách hàng"),
        dia_chi: str = Field(description="Địa chỉ khách hàng")
    ) -> dict:
        """
        Sử dụng công cụ này KHI VÀ CHỈ KHI khách hàng đã xác nhận đặt một dịch vụ sửa chữa.

        QUAN TRỌNG:
        1.  Các tham số `ma_dich_vu`, `ten_dich_vu`, và `ten_san_pham` BẮT BUỘC phải được lấy từ kết quả của công cụ `search_services_tool` đã được gọi trước đó và là dịch vụ khách hàng chốt.
        2.  TUYỆT ĐỐI KHÔNG được hỏi khách hàng mã dịch vụ. Luôn tự động lấy nó từ lịch sử tra cứu.
        3.  Trước khi gọi công cụ này, BẮT BUỘC phải hỏi và thu thập đủ thông tin cá nhân của khách hàng, bao gồm: `ten_khach_hang`, `so_dien_thoai`, và `dia_chi`.
        """
        print("--- LangChain Agent đã gọi công cụ tạo đơn hàng dịch vụ ---")
        print(f"Debug - loai_dich_vu type: {type(loai_dich_vu)}, value: {loai_dich_vu}")

        import time
        timestamp = str(int(time.time()))[-6:]  # Lấy 6 chữ số cuối của timestamp
        order_id = f"DHDV_{so_dien_thoai[-4:]}_{ma_dich_vu.split('-')[-1]}_{timestamp}"
        
        # Xử lý an toàn cho loai_dich_vu
        safe_loai_dich_vu = None
        if loai_dich_vu and str(loai_dich_vu).strip() and not str(loai_dich_vu).startswith('<'):
            safe_loai_dich_vu = str(loai_dich_vu).strip()
        
        # Lưu vào database
        db = next(get_db())
        try:
            new_order = ServiceOrder(
                order_id=order_id,
                customer_id=customer_id,
                thread_id=thread_id,
                ma_dich_vu=ma_dich_vu,
                ten_dich_vu=ten_dich_vu,
                loai_dich_vu=safe_loai_dich_vu,
                ten_san_pham_sua_chua=ten_san_pham,
                ten_khach_hang=ten_khach_hang,
                so_dien_thoai=so_dien_thoai,
                dia_chi=dia_chi,
                loai_don_hang="Dịch vụ"
            )
            db.add(new_order)
            db.commit()
            
            order_detail = {
                "order_id": order_id,
                "ma_dich_vu": ma_dich_vu,
                "ten_dich_vu": ten_dich_vu,
                "loai_dich_vu": safe_loai_dich_vu,
                "ten_san_pham_sua_chua": ten_san_pham,
                "ten_khach_hang": ten_khach_hang,
                "so_dien_thoai": so_dien_thoai,
                "dia_chi": dia_chi,
                "loai_don_hang": "Dịch vụ"
            }

            # Call Zalo API only if thread_id is valid
            zalo_result = None
            if validate_thread_id(thread_id):
                service_name = f"{ten_dich_vu} - {ten_san_pham}"
                zalo_result = call_zalo_api(customer_id, thread_id, ten_khach_hang, so_dien_thoai, dia_chi, service_name)
            
            success_message = f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}."
            if zalo_result and zalo_result["status"] == "success":
                success_message += " Đã tạo nhóm Zalo để theo dõi đơn hàng."
            elif zalo_result:
                success_message += f" Lưu ý: {zalo_result['message']}"

            return {
                "status": "success",
                "message": success_message,
                "order_detail": order_detail,
                # "zalo_result": zalo_result
            }
        except Exception as e:
            db.rollback()
            return {
                "status": "error",
                "message": f"Lỗi khi tạo đơn hàng: {str(e)}"
            }
        finally:
            db.close()
    
    return StructuredTool.from_function(
        func=create_order_service,
        name="create_order_service_tool",
        description="Tạo đơn hàng dịch vụ sửa chữa",
        args_schema=OrderServiceInput
    )

def create_order_accessory_tool_with_db(customer_id: str, thread_id: str):
    def create_order_accessory(
        ma_phu_kien: str = Field(description="Mã phụ kiện"),
        ten_phu_kien: str = Field(description="Tên phụ kiện"),
        so_luong: int = Field(description="Số lượng phụ kiện"),
        ten_khach_hang: str = Field(description="Tên khách hàng"),
        so_dien_thoai: str = Field(description="Số điện thoại khách hàng"),
        dia_chi: str = Field(description="Địa chỉ giao hàng")
    ) -> dict:
        """
        Sử dụng công cụ này KHI VÀ CHỈ KHI khách hàng đã xác nhận chốt đơn mua một phụ kiện.

        QUAN TRỌNG:
        1.  Tham số `ma_phu_kien` và `ten_phu_kien` BẮT BUỘC phải được lấy từ kết quả của công cụ `search_accessories_tool` đã được gọi trước đó trong cuộc trò chuyện và là phụ kiện khách hàng chốt.
        2.  TUYỆT ĐỐI KHÔNG được hỏi khách hàng mã phụ kiện. Luôn tự động lấy nó từ lịch sử tra cứu.
        3.  Trước khi gọi công cụ này, BẮT BUỘC phải hỏi và thu thập đủ thông tin cá nhân của khách hàng, bao gồm: `ten_khach_hang`, `so_dien_thoai`, và `dia_chi`.
        """
        print("--- LangChain Agent đã gọi công cụ tạo đơn hàng phụ kiện ---")

        import time
        timestamp = str(int(time.time()))[-6:]  # Lấy 6 chữ số cuối của timestamp
        order_id = f"DHPK_{so_dien_thoai[-4:]}_{ma_phu_kien.split('-')[-1]}_{timestamp}"
        
        # Lưu vào database
        db = next(get_db())
        try:
            new_order = AccessoryOrder(
                order_id=order_id,
                customer_id=customer_id,
                thread_id=thread_id,
                ma_phu_kien=ma_phu_kien,
                ten_phu_kien=ten_phu_kien,
                so_luong=so_luong,
                ten_khach_hang=ten_khach_hang,
                so_dien_thoai=so_dien_thoai,
                dia_chi=dia_chi,
                loai_don_hang="Phụ kiện"
            )
            db.add(new_order)
            db.commit()
            
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
            
            # Call Zalo API only if thread_id is valid
            zalo_result = None
            if validate_thread_id(thread_id):
                zalo_result = call_zalo_api(customer_id, thread_id, ten_khach_hang, so_dien_thoai, dia_chi, ten_phu_kien)
            
            success_message = f"Đã tạo đơn hàng thành công! Mã đơn hàng của bạn là {order_id}."
            if zalo_result and zalo_result["status"] == "success":
                success_message += " Đã tạo nhóm Zalo để theo dõi đơn hàng."
            elif zalo_result:
                success_message += f" Lưu ý: {zalo_result['message']}"
        
            return {
                "status": "success",
                "message": success_message,
                "order_detail": order_detail,
                # "zalo_result": zalo_result
            }
        except Exception as e:
            db.rollback()
            return {
                "status": "error",
                "message": f"Lỗi khi tạo đơn hàng: {str(e)}"
            }
        finally:
            db.close()
    
    return StructuredTool.from_function(
        func=create_order_accessory,
        name="create_order_accessory_tool",
        description="Tạo đơn hàng phụ kiện",
        args_schema=OrderAccessoryInput
    )

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
    thread_id: str,
    product_feature_enabled: bool = True,
    service_feature_enabled: bool = True, 
    accessory_feature_enabled: bool = True,
    llm: Optional[BaseLanguageModel] = None
) -> list:
    """
    Tạo một danh sách các tool dành riêng cho một khách hàng cụ thể.
    """
    tools = []
    
    # Always include document retrieval tool
    retrieve_document_tool = StructuredTool.from_function(
        func=partial(retrieve_document_logic, tenant_id=customer_id),
        name="retrieve_document_tool",
        description="Tìm kiếm thông tin chung, chính sách, hướng dẫn từ cơ sở tri thức",
        args_schema=RetrieveDocumentInput,
        coroutine=partial(retrieve_document_logic, tenant_id=customer_id)
    )
    tools.append(retrieve_document_tool)
    
    # Always include customer info checking tool
    check_customer_info_tool = create_check_customer_info_tool(customer_id, thread_id)
    tools.append(check_customer_info_tool)
    
    # Always include store info tool
    store_info_tool = create_get_store_info_tool(customer_id)
    tools.append(store_info_tool)
    
    available_tools = []
    
    if product_feature_enabled:
        customer_search_product_func = partial(search_products_logic, es_client=es_client, customer_id=customer_id, llm=llm)
        
        search_product_tool = StructuredTool.from_function(
            func=customer_search_product_func,
            name="search_products_tool",
            description=search_products_logic.__doc__,
            args_schema=SearchProductInput,
            coroutine=customer_search_product_func
        )
        # Tạo order tool với customer_id và thread_id được bind sẵn
        order_product_tool = create_order_product_tool_with_db(customer_id=customer_id, thread_id=thread_id)
        
        available_tools.extend([
            search_product_tool,
            order_product_tool,
        ])

    if service_feature_enabled:
        customer_search_service_func = partial(search_services_logic, es_client=es_client, customer_id=customer_id, llm=llm)
        
        search_service_tool = StructuredTool.from_function(
            func=customer_search_service_func,
            name="search_services_tool",
            description=search_services_logic.__doc__,
            args_schema=SearchServiceInput,
            coroutine=customer_search_service_func
        )
        
        # Tạo order tool với customer_id và thread_id được bind sẵn
        order_service_tool = create_order_service_tool_with_db(customer_id=customer_id, thread_id=thread_id)
        
        available_tools.extend([
            search_service_tool,
            order_service_tool,
        ])

    if accessory_feature_enabled:
        customer_search_accessory_func = partial(search_accessories_logic, es_client=es_client, customer_id=customer_id, llm=llm)
        
        search_accessory_tool = StructuredTool.from_function(
            func=customer_search_accessory_func,
            name="search_accessories_tool",
            description=search_accessories_logic.__doc__,
            args_schema=SearchAccessoryInput,
            coroutine=customer_search_accessory_func
        )

        # Tạo order tool với customer_id và thread_id được bind sẵn
        order_accessory_tool = create_order_accessory_tool_with_db(customer_id=customer_id, thread_id=thread_id)

        available_tools.extend([
            search_accessory_tool,
            order_accessory_tool,
        ])

    # Combine all tools
    tools.extend(available_tools)
    return tools
