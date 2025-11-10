import os
from sqlalchemy import create_engine, Column, String, Boolean, Text, Integer, LargeBinary, DateTime, UniqueConstraint
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

class StoreInfo(Base):
    __tablename__ = "store_info"

    customer_id = Column(String, primary_key=True, index=True)
    store_name = Column(String, nullable=True)
    store_address = Column(String, nullable=True)
    store_phone = Column(String, nullable=True)
    store_email = Column(String, nullable=True)
    store_website = Column(String, nullable=True)
    store_facebook = Column(String, nullable=True)
    store_address_map = Column(String, nullable=True)
    store_image = Column(String, nullable=True)
    info_more = Column(String, nullable=True)
    
class CustomerIsSale(Base):
    __tablename__ = "customer_is_sale"
    
    customer_id = Column(String, primary_key=True, index=True)
    thread_id = Column(String, primary_key=True, index=True)
    is_sale_customer = Column(Boolean, default=False, nullable=False)

class SystemInstruction(Base):
    __tablename__ = "system_instructions"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)

class SystemPromptProfile(Base):
    __tablename__ = "system_prompt_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=True)
    persona_template = Column(Text, nullable=True)
    tone_style = Column(Text, nullable=True)
    workflow_header = Column(Text, nullable=True)
    base_instructions = Column(Text, nullable=True)
    product_workflow = Column(Text, nullable=True)
    service_workflow = Column(Text, nullable=True)
    accessory_workflow = Column(Text, nullable=True)
    workflow_instructions = Column(Text, nullable=True)
    pagination_instruction = Column(Text, nullable=True)
    faq_instruction = Column(Text, nullable=True)
    faq_context_template = Column(Text, nullable=True)
    ocr_instruction = Column(Text, nullable=True)
    ocr_prefix_label = Column(String, nullable=True)
    chat_history_role_user = Column(String, nullable=True)
    chat_history_role_ai = Column(String, nullable=True)
    tool_retrieve_document_description = Column(Text, nullable=True)
    tool_check_customer_info_description = Column(Text, nullable=True)
    tool_get_store_info_description = Column(Text, nullable=True)
    tool_search_products_description = Column(Text, nullable=True)
    tool_create_order_product_description = Column(Text, nullable=True)
    tool_search_services_description = Column(Text, nullable=True)
    tool_create_order_service_description = Column(Text, nullable=True)
    tool_search_accessories_description = Column(Text, nullable=True)
    tool_create_order_accessory_description = Column(Text, nullable=True)
    tool_escalate_to_human_response = Column(Text, nullable=True)
    tool_end_conversation_response = Column(Text, nullable=True)
    filter_results_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    status = Column(String, default="Chưa gọi", nullable=False)
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
    status = Column(String, default="Chưa gọi", nullable=False)
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
    status = Column(String, default="Chưa gọi", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ChatCustomer(Base):
    __tablename__ = "chat_customers"
    
    customer_id = Column(String, primary_key=True, index=True)
    status = Column(String, default="active", nullable=False)  # active, stopped


class GraphRAGArtifact(Base):
    __tablename__ = "graphrag_artifacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(String, index=True, nullable=False)
    artifact_type = Column(String, nullable=False)  # entities, relationships, text_units, community_reports, ...
    row_id = Column(String, nullable=True)
    payload = Column(Text, nullable=False)  # JSON string of the row
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))



def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------
# Ingest & Prompt Versioning
# ------------------------

class IngestedMessage(Base):
    __tablename__ = "ingested_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String, nullable=False)
    external_message_id = Column(String, nullable=False)
    external_thread_id = Column(String, index=True, nullable=False)
    customer_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)  # 'human' | 'bot'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=True)
    rating = Column(Integer, nullable=True)  # -1 | 0 | 1
    content_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('source', 'external_message_id', name='uq_ingested_source_msg'),
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(String, index=True, nullable=False)
    version = Column(Integer, nullable=False)
    template = Column(Text, nullable=False)
    algo = Column(String, nullable=True)
    metrics = Column(Text, nullable=True)  # JSON string for metrics
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('customer_id', 'version', name='uq_prompt_version_customer'),
    )
