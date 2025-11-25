import json
import logging
import os
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict


SERVICE_NAME = os.getenv("SERVICE_NAME", "chatbotmobilestore-api")
LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "./logs")

_logger = logging.getLogger("chatbotmobilestore")
_configured = False


def _configure_logger() -> None:
    global _configured
    if _configured:
        return

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    _logger.setLevel(level)

    if not _logger.handlers:
        # Console handler (stdout)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(console_handler)

        # File handler for Filebeat to collect
        log_path = Path(LOG_DIR)
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_path / "app.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(file_handler)

    _logger.propagate = False
    _configured = True


def generate_error_ref_id() -> str:
    return uuid.uuid4().hex[:8].upper()


def log_json(payload: Dict[str, Any], level: str = "INFO") -> None:
    """Log any payload as JSON with automatic timestamp and service name."""
    _configure_logger()

    if "@timestamp" not in payload:
        payload["@timestamp"] = datetime.now(timezone.utc).isoformat()

    payload["log.level"] = level.upper()
    payload.setdefault("service.name", SERVICE_NAME)

    try:
        log_line = json.dumps(payload, ensure_ascii=False, default=str)
        log_method = getattr(_logger, level.lower(), _logger.info)
        log_method(log_line)
    except Exception:
        _logger.error("Failed to serialize log payload", exc_info=True)


def log_error(payload: Dict[str, Any]) -> None:
    """Log an error payload."""
    log_json(payload, level="ERROR")


def log_info(payload: Dict[str, Any]) -> None:
    """Log an info payload."""
    log_json(payload, level="INFO")


def log_warning(payload: Dict[str, Any]) -> None:
    """Log a warning payload."""
    log_json(payload, level="WARNING")
