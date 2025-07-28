from pydantic import BaseModel, Field
from typing import Optional

class SearchInput(BaseModel):
    """Input model for the search_iphones_tool."""
    # query_text: Optional[str] = Field(description="Truy vấn tìm kiếm bằng ngôn ngữ tự nhiên, ví dụ: 'iPhone màu xanh giá rẻ'.")
    model: Optional[str] = Field(description="Model cụ thể của iPhone, ví dụ: 'iPhone 15 Pro Max'.")
    mau_sac: Optional[str] = Field(description="Màu sắc của sản phẩm, ví dụ: 'Titan Tự nhiên'.")
    dung_luong: Optional[str] = Field(description="Dung lượng lưu trữ, ví dụ: '256GB'.")
    tinh_trang_may: Optional[str] = Field(description="Tình trạng của máy, ví dụ: 'Mới' hoặc 'Likenew'.")
    min_gia: Optional[float] = Field(description="Mức giá tối thiểu.")
    max_gia: Optional[float] = Field(description="Mức giá tối đa.")

class OrderInput(BaseModel):
    """Input model for the create_order_tool."""
    ma_san_pham: str = Field(description="Mã sản phẩm duy nhất của iPhone cần đặt hàng.")
    so_luong: int = Field(description="Số lượng sản phẩm muốn mua.")
    ten_khach_hang: str = Field(description="Họ và tên đầy đủ của người nhận hàng.")
    so_dien_thoai: str = Field(description="Số điện thoại liên lạc của người nhận.")
    dia_chi: str = Field(description="Địa chỉ chi tiết để giao hàng.") 