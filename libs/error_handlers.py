from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .responses import ErrorInfo, ErrorResponse


def _build_error_response(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return ErrorResponse(
        status="error",
        error=ErrorInfo(code=code, message=message, details=details, request_id=request_id),
    ).model_dump()


def _extract_request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return str(request_id)

    header_request_id = request.headers.get("X-Request-Id")
    if header_request_id:
        return header_request_id

    return None


def install_exception_handlers(app: FastAPI) -> None:
    """Ловит все ошибки и закидывает их в один формат ErrorResponse"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = _extract_request_id(request)
        detail_payload = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        raw_code = detail_payload.get("code", "http_error")
        code = raw_code if isinstance(raw_code, str) else "http_error"

        raw_message = detail_payload.get("message", "HTTP error")
        message = raw_message if isinstance(raw_message, str) else "HTTP error"

        raw_details = detail_payload.get("details")
        if isinstance(raw_details, dict):
            details = raw_details
        elif raw_details is None:
            details = detail_payload
        else:
            details = {"detail": raw_details}

        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_response(
                code=code,
                message=message,
                details=details,
                request_id=request_id,
            ),
            headers={"X-Request-Id": request_id} if request_id else None,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = _extract_request_id(request)
        return JSONResponse(
            status_code=422,
            content=_build_error_response(
                code="validation_error",
                message="Request validation failed",
                details={"errors": exc.errors()},
                request_id=request_id,
            ),
            headers={"X-Request-Id": request_id} if request_id else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _extract_request_id(request)
        return JSONResponse(
            status_code=500,
            content=_build_error_response(
                code="internal_error",
                message="Internal server error",
                details={"exception": exc.__class__.__name__},
                request_id=request_id,
            ),
            headers={"X-Request-Id": request_id} if request_id else None,
        )