def sanitize_es_id(identifier: str) -> str:
    """
    Làm sạch một định danh để sử dụng an toàn trong routing và ID của Elasticsearch.
    Thay thế dấu gạch ngang bằng dấu gạch dưới.
    """
    if identifier is None:
        return ""
    return identifier.replace("-", "_")
