import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


SERVICE_NAME = os.getenv("SERVICE_NAME", "chatbotmobilestore-api")
LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "INFO")

_logger = logging.getLogger("chatbotmobilestore")
_configured = False


def _configure_logger() -> None:
    global _configured
    if _configured:
        return

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    _logger.setLevel(level)

    if not _logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        _logger.addHandler(handler)

    _logger.propagate = False
    _configured = True


def generate_error_ref_id() -> str:
    return uuid.uuid4().hex[:8].upper()


def log_error(payload: Dict[str, Any]) -> None:
    _configure_logger()

    if "@timestamp" not in payload:
        payload["@timestamp"] = datetime.now(timezone.utc).isoformat()

    if "log.level" not in payload:
        payload["log.level"] = "ERROR"

    payload.setdefault("service.name", SERVICE_NAME)

    try:
        _logger.error(json.dumps(payload, ensure_ascii=False))
    except Exception:
        _logger.error("Failed to serialize log payload", exc_info=True)
