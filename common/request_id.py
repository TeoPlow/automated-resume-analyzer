import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


def get_request_id() -> str:
    """Получить ID текущего запроса из контекста."""
    return _request_id_var.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware: создаёт или пробрасывает X-Request-Id."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Установить request_id в контекст и добавить в заголовок ответа."""
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        _request_id_var.set(request_id)

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
