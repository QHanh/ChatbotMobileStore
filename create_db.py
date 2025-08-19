import os
import psycopg2
from urllib.parse import urlparse
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from database.database import init_db

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


if __name__ == "__main__":
    # Bước 1: Đảm bảo database tồn tại
    create_database_if_not_exists()
    
    # Bước 2: Tạo các bảng bên trong database đó
    print("Đang khởi tạo các bảng...")
    init_db()
    print("Khởi tạo bảng thành công.")
