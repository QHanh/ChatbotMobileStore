import os
from dotenv import load_dotenv
import json
import random

# Tải biến môi trường từ file .env
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELASTIC_HOST = os.getenv("ELASTIC_HOST")

# FastAPI Config
APP_CONFIG = {
    "title": "Chatbot Tư Vấn Bán Hàng - Cửa Hàng Điện Thoại Di Động",
    "description": "RAG Chatbot sử dụng Elasticsearch",
    "version": "1.0.0"
}

# CORS Config
CORS_CONFIG = {
    "allow_origins": ["*"],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}