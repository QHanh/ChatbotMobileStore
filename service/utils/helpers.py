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