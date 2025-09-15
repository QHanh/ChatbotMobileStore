import os
from sqlalchemy import create_engine, Column, String, Boolean, Text, Integer, LargeBinary, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from datetime import datetime

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
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatbotSettings(Base):
    __tablename__ = "chatbot_settings"

    customer_id = Column(String, primary_key=True, index=True)
    chatbot_icon_url = Column(String, nullable=True)
    chatbot_message_default = Column(String, nullable=True)
    chatbot_callout = Column(String, nullable=True)
    chatbot_name = Column(String, nullable=True)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
