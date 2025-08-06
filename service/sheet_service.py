import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Cấu hình ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file"
]

CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "config/credentials.json")

# --- Khởi tạo ---
def get_gspread_client():
    """Khởi tạo và trả về một client để tương tác với Google Sheets."""
    if not os.path.exists(CREDENTIALS_FILE):
        logger.warning(f"Không tìm thấy file credentials tại '{CREDENTIALS_FILE}'. Chức năng ghi vào Google Sheet sẽ bị vô hiệu hóa.")
        return None
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo Google Sheets client: {e}")
        return None

def get_worksheet(client, spreadsheet_id: str, worksheet_name: str):
    """Lấy một worksheet cụ thể từ spreadsheet."""
    if not client or not spreadsheet_id:
        return None
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Worksheet '{worksheet_name}' không tồn tại, đang tạo mới...")
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="100", cols="20")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Lỗi: Không tìm thấy Spreadsheet với ID '{spreadsheet_id}'. Hãy chắc chắn rằng bạn đã chia sẻ sheet với email của service account.")
        return None
    except Exception as e:
        logger.error(f"Lỗi khi truy cập worksheet: {e}")
        return None

# --- Chức năng ---
def insert_order_to_sheet(spreadsheet_id: str, worksheet_name: str, order_data: Dict[str, Any]):
    """
    Chèn một dòng dữ liệu đơn hàng vào worksheet được chỉ định.
    """
    client = get_gspread_client()
    worksheet = get_worksheet(client, spreadsheet_id, worksheet_name)

    if not worksheet:
        logger.warning("Không thể chèn dữ liệu do lỗi kết nối hoặc cấu hình sheet.")
        return False

    try:
        # Thêm cột 'timestamp'
        order_data_with_ts = order_data.copy()
        order_data_with_ts['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers = worksheet.row_values(1)
        if not headers:
            headers = list(order_data_with_ts.keys())
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            logger.info(f"Đã tạo header cho worksheet '{worksheet_name}'.")

        # Đảm bảo tất cả các key trong order_data_with_ts đều có trong header
        new_headers = [h for h in order_data_with_ts.keys() if h not in headers]
        if new_headers:
             worksheet.append_cols([new_headers])


        # Tạo list giá trị theo đúng thứ tự của header hiện tại
        current_headers = worksheet.row_values(1)
        row_to_insert = [order_data_with_ts.get(header, "") for header in current_headers]
        
        worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        logger.info(f"Đã chèn thành công đơn hàng vào Google Sheet '{worksheet_name}'.")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi chèn dữ liệu vào Google Sheet: {e}")
        return False
