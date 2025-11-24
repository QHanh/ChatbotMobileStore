from typing import Any, Dict

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

import traceback

from app_logging.logger import log_error, generate_error_ref_id


def _build_payload_from_exception(
    request: Request,
    exc: Exception,
    *,
    default_action: str,
    status_code: int,
    message: str,
    error_code: str,
    error_ref_id: str,
) -> Dict[str, Any]:
    base_payload: Dict[str, Any] = {}

    ctx = getattr(exc, "log_context", None)
    if isinstance(ctx, dict):
        base_payload.update(ctx)

    base_payload.setdefault("event.action", default_action)
    base_payload.setdefault("event.category", "error")
    base_payload.setdefault("source.layer", "middleware")
    base_payload.setdefault("source.controller", "error_handler")
    base_payload.setdefault("source.function", "ErrorHandlerMiddleware.dispatch")

    trace_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
    if trace_id:
        base_payload.setdefault("trace.id", trace_id)

    stack_trace = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )

    base_payload.update(
        {
            "message": message,
            "error.type": exc.__class__.__name__,
            "error.code": error_code,
            "error.ref_id": error_ref_id,
            "http.status_code": status_code,
            "request.method": request.method,
            "request.path": str(request.url.path),
            "request.query": str(request.url.query),
            "error.stack_trace": stack_trace,
        }
    )

    return base_payload


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            error_ref_id = generate_error_ref_id()
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)

            payload = _build_payload_from_exception(
                request,
                e,
                default_action="http_exception",
                status_code=e.status_code,
                message=detail,
                error_code=f"HTTP_{e.status_code}",
                error_ref_id=error_ref_id,
            )

            log_error(payload)
            raise
        except Exception as e:  # noqa: BLE001
            error_ref_id = generate_error_ref_id()

            payload = _build_payload_from_exception(
                request,
                e,
                default_action="unhandled.exception",
                status_code=500,
                message="Unhandled exception in ChatbotMobileStore",
                error_code="INTERNAL_SERVER_ERROR",
                error_ref_id=error_ref_id,
            )

            log_error(payload)
            raise
