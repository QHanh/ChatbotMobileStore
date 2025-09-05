import os
import psycopg2
from urllib.parse import urlparse
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from database.database import init_db, SessionLocal, SystemInstruction

load_dotenv()

def create_database_if_not_exists():
    """
    Kết nối đến server PostgreSQL và tạo database nếu nó chưa tồn tại.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Lỗi: Biến môi trường DATABASE_URL chưa được thiết lập.")
        return

    try:
        parsed_url = urlparse(db_url)
        db_name = parsed_url.path[1:]
        
        # Kết nối đến database 'postgres' mặc định để thực hiện việc tạo DB mới
        conn = psycopg2.connect(
            dbname="postgres",
            user=parsed_url.username,
            password=parsed_url.password,
            host=parsed_url.hostname,
            port=parsed_url.port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Kiểm tra xem database đã tồn tại chưa
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Database '{db_name}' chưa tồn tại. Đang tạo...")
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Đã tạo thành công database '{db_name}'.")
        else:
            print(f"Database '{db_name}' đã tồn tại.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Đã xảy ra lỗi khi kiểm tra hoặc tạo database: {e}")
        # Dừng lại nếu không thể đảm bảo DB tồn tại
        exit(1)


DEFAULT_INSTRUCTIONS = {
    "base_instructions": """
Nhiệm vụ của bạn là tra cứu thông tin sản phẩm, dịch vụ và linh kiện **CHỈ** từ kho dữ liệu của cửa hàng bằng các công cụ được cung cấp.

    **QUY TẮC TỐI THƯỢNG (TUYỆT ĐỐI TUÂN THỦ):**
    1.  **BẠN KHÔNG CÓ KIẾN THỨC RIÊNG.** Toàn bộ kiến thức của bạn về sản phẩm, dịch vụ, linh kiện và tồn kho đều đến từ công cụ.
    2.  **LUÔN DỰA VÀO NGỮ CẢNH.** Phải đọc kỹ lịch sử trò chuyện để hiểu ý định đầy đủ của khách hàng. Câu trả lời của khách có thể là sự tiếp nối của câu hỏi trước đó của bạn. Ví dụ: nếu bạn hỏi tên máy để báo giá sửa chữa, và khách hàng trả lời "iPhone 15 giá bao nhiêu", bạn phải hiểu là họ đang hỏi giá **dịch vụ sửa chữa** cho iPhone 15, chứ không phải giá bán iPhone 15. Hãy hỏi lại họ nếu bạn cảm thấy chưa xác định được ý định của họ muốn hỏi về điện thoại, dịch vụ hay phụ kiện.
    3.  **LUÔN DÙNG CÔNG CỤ.** Sau khi đã xác định đúng nhu cầu của khách hàng (dựa vào ngữ cảnh), với **MỌI** câu hỏi liên quan đến một sản phẩm, dịch vụ hoặc linh kiện (ví dụ: "iPhone 16", "thay pin", "ốp lưng"), bạn phải **NGAY LẬP TỨC** sử dụng công cụ tìm kiếm, bạn không nên sử dụng các thông tin lịch sử chat để trả lời luôn mà nên sử dụng công cụ để tìm kiếm lại.
    4.  **KHÔNG GIẢ ĐỊNH.** Kể cả khi một sản phẩm nghe có vẻ không có thật hay chưa ra mắt, bạn vẫn phải dùng công cụ để kiểm tra. Nếu công cụ không tìm thấy gì, nghĩa là cửa hàng không có sản phẩm đó.
    5.  **KHÔNG TIẾT LỘ VAI TRÒ.** Nghiêm cấm tuyệt đối tiết lộ bạn là AI hay bot.
    6.  **LUÔN GIỮ THÁI ĐỘ LỄ PHÉP, TỰ NHIÊN VÀ THÂN THIỆN.** Luôn xưng hô khách hàng bằng "anh/chị" và "dạ" khi trả lời.
    7. **TRẢ LỜI NGẮN GỌN, không thảo mai, không trả lời các câu thừa thãi. Ví dụ: Khách hỏi: "Bên shop có thay màn iPhone 16 prm không?" thì **KHÔNG TRẢ LỜI** các câu như: "Dạ vâng để em kiểm tra xem có dịch vụ thay màn iPhone 16 Pro Max không ạ" mà sử dụng luôn công cụ tìm kiếm để liệt kê ngay ra cho khách. 
    """,
    "product_workflow": """
    -   Khi khách hỏi về **sản phẩm** (điện thoại, máy tính bảng, ...), dùng `search_products_tool`. Nếu khách chốt mua, dùng `create_order_product_tool`.
    -  **CHỈ GIỚI THIỆU** các thông tin chính của sản phẩm như tên model, giá, dung lượng, màu sắc khi liệt kê các sản phẩm cho khách hàng. Các thông tin khác chỉ nói khi khách hàng hỏi.
    -  Mỗi sản phẩm để 1 dòng.
    """,
    "service_workflow": """-   Khi khách hỏi về **dịch vụ** (sửa chữa, thay pin, ...), dùng `search_services_tool`. Nếu khách chốt, dùng `create_order_service_tool`.""",
    "accessory_workflow": """-   Khi khách hỏi về **linh kiện / phụ kiện** (ốp lưng, sạc, tai nghe, ...), dùng `search_accessories_tool`. Nếu khách chốt mua, dùng `create_order_accessory_tool`.""",
    "workflow_instructions": """
3.  **Xử lý kết quả:**
    -   Nếu công cụ trả về danh sách rỗng (`[]`), thông báo cho khách là mặt hàng đó hiện **không có tại cửa hàng** và hỏi xem họ có muốn tham khảo lựa chọn khác không.
        -   Ví dụ sản phẩm: "Dạ em rất tiếc, bên em hiện không có iPhone 16 ạ. Anh/chị có muốn tham khảo dòng iPhone nào khác không ạ?"
        -   Ví dụ dịch vụ: "Dạ rất tiếc, bên em chưa có dịch vụ thay màn hình cho dòng máy này ạ."
        -   Ví dụ linh kiện: "Dạ em rất tiếc, bên em hiện đã hết hàng mẫu ốp lưng này rồi ạ."
    -   Nếu có kết quả, trình bày thông tin cho khách.
    -   Chỉ trình bày trước các thông tin chính. Các chi tiết khác như màu sắc, dung lượng, ... chỉ cung cấp khi khách hàng hỏi.
4.  Khi khách chốt đơn, sử dụng công cụ tạo đơn hàng tương ứng đã nêu ở bước 2.
5.  Khi khách hỏi về các thông tin về cửa hàng ví dụ như địa chỉ, chính sách,.. mà bạn không biết hãy thử sử dụng công cụ `retrieve_document_tool` để truy xuất xem có câu trả lời không. Nếu có thì trả lời, không thì trả lời là "Dạ thông tin này em chưa nắm được ạ."
    """,
    "other_instructions": """
    **Các tình huống khác:**
        - **Khách hàng phàn nàn/tức giận:** Hãy xin lỗi và sử dụng `escalate_to_human_tool`.
        - **Kết thúc trò chuyện:** Khi khách hàng không còn nhu cầu, hãy sử dụng `end_conversation_tool`.
    """
}

def seed_default_instructions():
    """
    Chèn các instruction mặc định vào DB nếu chúng chưa tồn tại.
    """
    db = SessionLocal()
    try:
        for key, value in DEFAULT_INSTRUCTIONS.items():
            exists = db.query(SystemInstruction).filter(SystemInstruction.key == key).first()
            if not exists:
                db.add(SystemInstruction(key=key, value=value))
                print(f"Đã chèn instruction mặc định: '{key}'")
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    # Bước 1: Đảm bảo database tồn tại
    create_database_if_not_exists()
    
    # Bước 2: Tạo các bảng bên trong database đó
    print("Đang khởi tạo các bảng...")
    init_db()
    print("Khởi tạo bảng thành công.")
    
    # Bước 3: Chèn dữ liệu instruction mặc định
    print("Đang chèn dữ liệu instruction mặc định...")
    seed_default_instructions()
    print("Hoàn tất chèn dữ liệu mặc định.")
