import functools
import inspect
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar, Union


F = TypeVar("F", bound=Callable[..., Any])


def _attach_log_context(
    exc: BaseException,
    *,
    event_action: str,
    event_category: str,
    source_layer: str,
    source_controller: str,
    source_function: str,
) -> None:
    existing: Optional[Dict[str, Any]] = getattr(exc, "log_context", None)  # type: ignore[assignment]
    if not isinstance(existing, dict):
        existing = {}

    existing.setdefault("event.action", event_action)
    existing.setdefault("event.category", event_category)
    existing.setdefault("source.layer", source_layer)
    existing.setdefault("source.controller", source_controller)
    existing.setdefault("source.function", source_function)

    setattr(exc, "log_context", existing)


def with_log_context(
    *,
    event_action: str,
    event_category: str,
    source_layer: str,
    source_controller: str,
    source_function: Optional[str] = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        is_coro = inspect.iscoroutinefunction(func)
        func_name = source_function or func.__name__

        if is_coro:

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    _attach_log_context(
                        exc,
                        event_action=event_action,
                        event_category=event_category,
                        source_layer=source_layer,
                        source_controller=source_controller,
                        source_function=func_name,
                    )
                    raise

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                _attach_log_context(
                    exc,
                    event_action=event_action,
                    event_category=event_category,
                    source_layer=source_layer,
                    source_controller=source_controller,
                    source_function=func_name,
                )
                raise

        return sync_wrapper  # type: ignore[return-value]

    return decorator
