from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.exceptions import AppError
from common.request_id import get_request_id


def register_error_handlers(app: FastAPI) -> None:
    """Зарегистрировать единые обработчики ошибок на приложении."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """Обработчик бизнес-ошибок приложения."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": get_request_id(),
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """Обработчик стандартных HTTP-ошибок."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {
                    "code": "http_error",
                    "message": str(exc.detail),
                    "details": {},
                    "request_id": get_request_id(),
                },
            },
        )
