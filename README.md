# Chatbot Agent

Dự án này xây dựng một ứng dụng chatbot đa người dùng. Chatbot được thiết kế cho các cửa hàng kinh doanh sửa chữa điện thoại, cho phép chủ cửa hàng tạo và cấu hình trợ lý bán hàng AI của riêng mình, có khả năng tư vấn cả về sản phẩm và dịch vụ dựa trên dữ liệu do chính cửa hàng cung cấp.

## Các tính năng chính

- **Đa người dùng**: Mỗi user có thể tự cấu hình thêm cho chatbot riêng biệt, hoàn toàn độc lập.
- **Truy xuất dữ liệu**: Sử dụng Elasticsearch để truy xuất dữ liệu chính xác và tốc độ nhanh.
- **Quản lý dữ liệu động**: API Upload, insert, update và delete dữ liệu sản phẩm và dịch vụ vào cơ sở dữ liệu nhanh chóng.
- **Agent AI**: Agent sử dụng "function calling" để thực hiện công việc.
