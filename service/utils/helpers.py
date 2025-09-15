import requests
from bs4 import BeautifulSoup

def get_text_from_url(url: str) -> str:
    """Fetches the content of a URL and returns the text."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.get_text(separator='\n', strip=True)
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Error fetching URL: {e}")

def sanitize_for_es(identifier: str) -> str:
    """Làm sạch một định danh để sử dụng an toàn trong routing và ID của Elasticsearch."""
    if not identifier:
        return ""
    return identifier.replace("-", "")

def sanitize_for_weaviate(identifier: str) -> str:
    """Làm sạch một định danh để sử dụng an toàn làm Weaviate tenant ID."""
    if not identifier:
        return ""
    sanitized = identifier.replace("-", "_")
    if sanitized and sanitized[0].isdigit():
        return f"t_{sanitized}"
    return sanitized