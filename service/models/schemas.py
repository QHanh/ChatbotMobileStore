from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class BulkDeleteInput(BaseModel):
    """Input model for bulk delete operations."""
    ids: List[str] = Field(description="A list of document IDs to delete.")

class FaqRow(BaseModel):
    """Input model for a single FAQ entry."""
    faq_id: str = Field(description="The unique identifier for the FAQ.")
    question: str = Field(description="The question.")
    answer: str = Field(description="The answer to the question.")

class FaqCreate(BaseModel):
    """Input model for creating a new FAQ entry."""
    question: str = Field(description="The question.")
    answer: str = Field(description="The answer to the question.")

class SearchProductInput(BaseModel):
    """Input model for the search_iphones_tool."""
    thread_id: Optional[str] = Field(default=None, description="ID luồng chat của người dùng.")
    model: Optional[str] = Field(default=None, description="Model cụ thể của iPhone, ví dụ: 'iPhone 15 Pro Max'.")
    mau_sac: Optional[str] = Field(default=None, description="Màu sắc của sản phẩm, ví dụ: 'Titan Tự nhiên'.")
    dung_luong: Optional[str] = Field(default=None, description="Dung lượng lưu trữ, ví dụ: '256GB'.")
    tinh_trang_may: Optional[str] = Field(default=None, description="Tình trạng của máy, ví dụ: 'đẹp', 'trầy xước', 'xước nhẹ', tùy theo khách hàng hỏi.")
    loai_thiet_bi: Optional[str] = Field(default=None, description="Loại thiết bị, ví dụ: 'Cũ', 'Mới'.")
    min_gia: Optional[float] = Field(default=None, description="Mức giá tối thiểu.")
    max_gia: Optional[float] = Field(default=None, description="Mức giá tối đa.")
    offset: Optional[int] = Field(default=0, description="Số lượng kết quả bỏ qua, dùng để xem các trang kết quả tiếp theo. Ví dụ offset=10 để xem trang 2.")

class SearchServiceInput(BaseModel):
    """Input model for the search_services_tool."""
    thread_id: Optional[str] = Field(default=None, description="ID luồng chat của người dùng.")
    ten_dich_vu: Optional[str] = Field(default=None, description="Tên dịch vụ, ví dụ: 'Thay pin'.")
    ten_san_pham: Optional[str] = Field(default=None, description="Tên sản phẩm điện thoại được sửa chữa, ví dụ: 'iPhone 15 Pro Max'.")
    loai_dich_vu: Optional[str] = Field(default=None, description="Loại dịch vụ, ví dụ: 'Pin Lithium', 'fix sọc'.")
    min_gia: Optional[float] = Field(default=None, description="Mức giá tối thiểu.")
    max_gia: Optional[float] = Field(default=None, description="Mức giá tối đa.")
    offset: Optional[int] = Field(default=0, description="Số lượng kết quả bỏ qua, dùng để xem các trang kết quả tiếp theo. Ví dụ offset=10 để xem trang 2.")

class SearchAccessoryInput(BaseModel):
    """Input model for the search_accessories_tool."""
    thread_id: Optional[str] = Field(default=None, description="ID luồng chat của người dùng.")
    ten_phu_kien: Optional[str] = Field(default=None, description="Tên phụ kiện, bạn cứ ghi đầy đủ tên phụ kiện, ví dụ: 'Kính hiển vi KAISI', 'Phản quang Oppo F3'.")
    phan_loai_phu_kien: Optional[str] = Field(default=None, description="Phân loại phụ kiện")
    thuoc_tinh_phu_kien: Optional[str] = Field(default=None, description="Thuộc tính phụ kiện, ví dụ: 'màu sắc', 'cỡ', 'loại',....")
    min_gia: Optional[float] = Field(default=None, description="Mức giá tối thiểu.")
    max_gia: Optional[float] = Field(default=None, description="Mức giá tối đa.")
    offset: Optional[int] = Field(default=0, description="Số lượng kết quả bỏ qua, dùng để xem các trang kết quả tiếp theo. Ví dụ offset=10 để xem trang 2.")

class RetrieveDocumentInput(BaseModel):
    """Input model for the retrieve_document_tool."""
    query: str = Field(description="Truy vấn tìm kiếm bằng ngôn ngữ tự nhiên, bạn nên dựa vào lịch sử hội thoại để viết lại câu hỏi của khách hàng đầy đủ ngữ nghĩa nhất để truy xuất dữ liệu, ví dụ: 'iPhone màu xanh giá rẻ'.")

class OrderProductInput(BaseModel):
    """Input model for the create_order_product_tool."""
    ma_san_pham: str = Field(description="Mã sản phẩm khách hàng đặt.")
    ten_san_pham: str = Field(description="Tên sản phẩm khách hàng đặt.")
    so_luong: int = Field(description="Số lượng sản phẩm muốn mua.")
    ten_khach_hang: str = Field(description="Họ và tên đầy đủ của người mua.")
    so_dien_thoai: str = Field(description="Số điện thoại liên lạc của người mua.")
    dia_chi: str = Field(description="Địa chỉ người mua.")

class OrderServiceInput(BaseModel):
    """Input model for the create_order_service_tool."""
    ma_dich_vu: str = Field(description="Mã dịch vụ khách hàng đặt.")
    ten_dich_vu: str = Field(description="Tên dịch vụ khách hàng đặt.")
    loai_dich_vu: Optional[str] = Field(default=None, description="Loại dịch vụ, ví dụ: 'Pin Lithium', 'Thay màn hình'.")
    ten_san_pham: str = Field(description="Tên sản phẩm điện thoại được sửa chữa.")
    ten_khach_hang: str = Field(description="Họ và tên đầy đủ của người mua.")
    so_dien_thoai: str = Field(description="Số điện thoại liên lạc của người mua.")
    dia_chi: str = Field(description="Địa chỉ người mua.")

class OrderAccessoryInput(BaseModel):
    """Input model for the create_order_accessory_tool."""
    ma_phu_kien: str = Field(description="Mã phụ kiện khách hàng đặt.")
    ten_phu_kien: str = Field(description="Tên phụ kiện khách hàng đặt.")
    so_luong: int = Field(description="Số lượng phụ kiện muốn mua.")
    ten_khach_hang: str = Field(description="Họ và tên đầy đủ của người mua.")
    so_dien_thoai: str = Field(description="Số điện thoại liên lạc của người mua.")
    dia_chi: str = Field(description="Địa chỉ người mua.")


class ChatbotRequest(BaseModel):
    """Input model for the chatbot."""
    query: str = Field(description="The user's query for the chatbot.")
    customer_id: str = Field(description="The unique identifier for the store owner.")
    llm_provider: Optional[str] = Field(default="google_genai", description="The LLM provider to use, e.g., 'google_genai' or 'openai'.")
    api_key: Optional[str] = Field(description="The API key for the LLM provider.")
    access: Optional[int] = Field(default=100, description="The access of the customer, e.g., '100' for test, '0' for not response, '1' for product, '2' for service, '3' for accessory, '12' for product and service, '13' for product and accessory, '23' for service and accessory, '123' for product, service and accessory.")

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

class AccessoryFeatureConfig(BaseModel):
    """Input model for enabling or disabling the accessory consultation feature."""
    enabled: bool = Field(description="Bật (true) hoặc tắt (false) chức năng tư vấn phụ kiện.")

class ProductFeatureConfig(BaseModel):
    """Input model for enabling or disabling the product consultation feature."""
    enabled: bool = Field(description="Bật (true) hoặc tắt (false) chức năng tư vấn sản phẩm.")

class ProductRow(BaseModel):
    ma_san_pham: str
    model: str
    mau_sac: Optional[str] = None
    dung_luong: Optional[str] = None
    bao_hanh: Optional[str] = None
    tinh_trang_may: Optional[str] = None
    loai_thiet_bi: Optional[str] = None
    tinh_trang_pin: Optional[float] = None
    gia: Optional[float] = None
    gia_buon: Optional[float] = None
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
    mau_sac_san_pham: Optional[str] = None
    loai_dich_vu: Optional[str] = None
    gia: Optional[float] = None
    gia_buon: Optional[float] = None
    bao_hanh: Optional[str] = None
    ghi_chu: Optional[str] = None

class AccessoryRow(BaseModel):
    accessory_code: str
    accessory_name: str
    category: Optional[str] = None
    properties: Optional[str] = None
    lifecare_price: Optional[float] = None
    sale_price: Optional[float] = None
    trademark: Optional[str] = None
    guarantee: Optional[str] = None
    inventory: Optional[int] = None
    specifications: Optional[str] = None
    avatar_images: Optional[str] = None
    link_accessory: Optional[str] = None

class DocumentInput(BaseModel):
    """Input model for adding a document."""
    text: str = Field(description="Nội dung văn bản thô cần thêm vào cơ sở dữ liệu vector.")
    source: Optional[str] = Field(default=None, description="Tên nguồn của văn bản, ví dụ: 'faq.txt'. Nếu không cung cấp, sẽ được gán một tên mặc định.")

class DocumentUrlInput(BaseModel):
    """Input model for adding a document from a URL."""
    url: str = Field(description="The URL of the document to add.")
    source: Optional[str] = Field(default=None, description="The source name for the document. If not provided, the URL will be used as the source.")

class Instruction(BaseModel):
    """Represents a single instruction key-value pair."""
    key: str
    value: str

class InstructionsUpdate(BaseModel):
    """Input model for updating system instructions."""
    instructions: List[Instruction]
    
class ChatHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    customer_id: str
    thread_id: str
    thread_name: Optional[str] = None
    role: str
    message: str

class ChatbotSettingsBase(BaseModel):
    chatbot_icon_url: Optional[str] = None
    chatbot_message_default: Optional[str] = None
    chatbot_callout: Optional[str] = None
    chatbot_name: Optional[str] = None

class ChatbotSettingsCreate(ChatbotSettingsBase):
    customer_id: str

class ChatbotSettingsUpdate(ChatbotSettingsBase):
    pass

class ChatbotSettings(ChatbotSettingsBase):
    model_config = ConfigDict(from_attributes=True)
    
    customer_id: str