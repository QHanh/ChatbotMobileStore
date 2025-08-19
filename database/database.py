import os
from sqlalchemy import create_engine, Column, String, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

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
    service_feature_enabled = Column(Boolean, default=False)
    accessory_feature_enabled = Column(Boolean, default=False)

class SystemInstruction(Base):
    __tablename__ = "system_instructions"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
