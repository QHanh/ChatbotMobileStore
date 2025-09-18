import os
from sqlalchemy import create_engine, Column, String, Boolean, Text, Integer, LargeBinary, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String, primary_key=True, index=True)
    ai_name = Column(String, nullable=True)
    ai_role = Column(String, nullable=True)
    custom_prompt = Column(String, nullable=True)
    service_feature_enabled = Column(Boolean, default=True)
    accessory_feature_enabled = Column(Boolean, default=True)
    product_feature_enabled = Column(Boolean, default=True)
    
class CustomerIsSale(Base):
    __tablename__ = "customer_is_sale"
    
    customer_id = Column(String, primary_key=True, index=True)
    thread_id = Column(String, primary_key=True, index=True)
    is_sale_customer = Column(Boolean, default=False, nullable=False)

class SystemInstruction(Base):
    __tablename__ = "system_instructions"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)

class ChatThread(Base):
    __tablename__ = "chat_threads"

    customer_id = Column(String, primary_key=True, index=True)
    thread_id = Column(String, primary_key=True, index=True)
    thread_name = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    thread_name = Column(String, nullable=True)
    role = Column(String, nullable=False)
    message = Column(Text, nullable=False)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(String, index=True, nullable=False)
    source_name = Column(String, nullable=False)
    file_name = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    full_content = Column(Text, nullable=True)
    file_content = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ChatbotSettings(Base):
    __tablename__ = "chatbot_settings"

    customer_id = Column(String, primary_key=True, index=True)
    chatbot_icon_url = Column(String, nullable=True)
    chatbot_message_default = Column(String, nullable=True)
    chatbot_callout = Column(String, nullable=True)
    chatbot_name = Column(String, nullable=True)

class ProductOrder(Base):
    __tablename__ = "product_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(String, unique=True, index=True, nullable=False)
    customer_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    ma_san_pham = Column(String, nullable=False)
    ten_san_pham = Column(String, nullable=False)
    so_luong = Column(Integer, nullable=False)
    ten_khach_hang = Column(String, nullable=False)
    so_dien_thoai = Column(String, nullable=False)
    dia_chi = Column(Text, nullable=False)
    loai_don_hang = Column(String, default="Sản phẩm", nullable=False)
    is_called = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(String, unique=True, index=True, nullable=False)
    customer_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    ma_dich_vu = Column(String, nullable=False)
    ten_dich_vu = Column(String, nullable=False)
    loai_dich_vu = Column(String, nullable=True)
    ten_san_pham_sua_chua = Column(String, nullable=False)
    ten_khach_hang = Column(String, nullable=False)
    so_dien_thoai = Column(String, nullable=False)
    dia_chi = Column(Text, nullable=False)
    loai_don_hang = Column(String, default="Dịch vụ", nullable=False)
    is_called = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AccessoryOrder(Base):
    __tablename__ = "accessory_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(String, unique=True, index=True, nullable=False)
    customer_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    ma_phu_kien = Column(String, nullable=False)
    ten_phu_kien = Column(String, nullable=False)
    so_luong = Column(Integer, nullable=False)
    ten_khach_hang = Column(String, nullable=False)
    so_dien_thoai = Column(String, nullable=False)
    dia_chi = Column(Text, nullable=False)
    loai_don_hang = Column(String, default="Phụ kiện", nullable=False)
    is_called = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ChatCustomer(Base):
    __tablename__ = "chat_customers"
    
    customer_id = Column(String, primary_key=True, index=True)
    status = Column(String, default="active", nullable=False)  # active, stopped



def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
