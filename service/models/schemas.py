from pydantic import BaseModel, Field
from typing import Optional

class SearchProductInput(BaseModel):
    """Input model for the search_iphones_tool."""
    # query_text: Optional[str] = Field(description="Truy vấn tìm kiếm bằng ngôn ngữ tự nhiên, ví dụ: 'iPhone màu xanh giá rẻ'.")
    model: Optional[str] = Field(description="Model cụ thể của iPhone, ví dụ: 'iPhone 15 Pro Max'.")
    mau_sac: Optional[str] = Field(description="Màu sắc của sản phẩm, ví dụ: 'Titan Tự nhiên'.")
    dung_luong: Optional[str] = Field(description="Dung lượng lưu trữ, ví dụ: '256GB'.")
    tinh_trang_may: Optional[str] = Field(description="Tình trạng của máy, ví dụ: 'cũ', 'mới', 'đẹp', 'trầy xước', tùy theo khách hàng hỏi.")
    min_gia: Optional[float] = Field(description="Mức giá tối thiểu.")
    max_gia: Optional[float] = Field(description="Mức giá tối đa.")

class SearchServiceInput(BaseModel):
    """Input model for the search_services_tool."""
    ten_dich_vu: Optional[str] = Field(description="Tên dịch vụ, ví dụ: 'Thay pin'.")
    ten_san_pham: Optional[str] = Field(description="Tên sản phẩm điện thoại được sửa chữa, ví dụ: 'iPhone 15 Pro Max'.")
    hang_dich_vu: Optional[str] = Field(description="Hãng dịch vụ, ví dụ: 'Pin Lithium'.")

class OrderProductInput(BaseModel):
    """Input model for the create_order_product_tool."""
    ma_san_pham: str = Field(description="Mã sản phẩm khách hàng đặt.")
    so_luong: int = Field(description="Số lượng sản phẩm muốn mua.")
    ten_khach_hang: str = Field(description="Họ và tên đầy đủ của người mua.")
    so_dien_thoai: str = Field(description="Số điện thoại liên lạc của người mua.")
    dia_chi: str = Field(description="Địa chỉ người mua.")

class OrderServiceInput(BaseModel):
    """Input model for the create_order_service_tool."""
    ma_dich_vu: str = Field(description="Mã dịch vụ khách hàng đặt.")
    so_luong: int = Field(description="Số lượng dịch vụ muốn mua.")
    ten_khach_hang: str = Field(description="Họ và tên đầy đủ của người mua.")
    so_dien_thoai: str = Field(description="Số điện thoại liên lạc của người mua.")
    dia_chi: str = Field(description="Địa chỉ người mua.")

class ChatbotRequest(BaseModel):
    """Input model for the chatbot."""
    query: str = Field(description="The user's query for the chatbot.")
    customer_id: str = Field(description="The unique identifier for the store owner.")
    llm_provider: Optional[str] = Field(default="google_genai", description="The LLM provider to use, e.g., 'google_genai' or 'openai'.")

class PersonaConfig(BaseModel):
    """Input model for configuring the AI's persona."""
    ai_name: str = Field(description="The name of the AI assistant, e.g., 'Mai'.")
    ai_role: str = Field(description="The role of the AI assistant, e.g., 'nhân viên tư vấn điện thoại'.")

class PromptConfig(BaseModel):
    """Input model for adding custom system prompt instructions."""
    custom_prompt: str = Field(description="Additional instructions to be added to the system prompt.") 

class ServiceFeatureConfig(BaseModel):
    """Input model for enabling or disabling the service consultation feature."""
    enabled: bool = Field(description="Bật (true) hoặc tắt (false) chức năng tư vấn dịch vụ.")

class ProductRow(BaseModel):
    ma_san_pham: str
    model: str
    mau_sac: Optional[str] = None
    dung_luong: Optional[str] = None
    bao_hanh: Optional[str] = None
    tinh_trang_may: Optional[str] = None
    tinh_trang_pin: Optional[float] = None
    gia: Optional[float] = None
    ton_kho: Optional[int] = None
    ghi_chu: Optional[str] = None
    ra_mat: Optional[str] = None
    man_hinh: Optional[str] = None
    chip_ram: Optional[str] = None
    camera: Optional[str] = None
    pin_mah: Optional[str] = None
    ket_noi_hdh: Optional[str] = None
    mau_sac_tieng_anh: Optional[str] = None
    mau_sac_available: Optional[str] = None
    dung_luong_available: Optional[str] = None
    kich_thuoc_trong_luong: Optional[str] = None

class ServiceRow(BaseModel):
    ma_dich_vu: str
    ten_dich_vu: str
    hang_san_pham: Optional[str] = None
    ten_san_pham: Optional[str] = None
    hang_dich_vu: Optional[str] = None
    gia: Optional[float] = None
    bao_hanh: Optional[str] = None
    ghi_chu: Optional[str] = None 