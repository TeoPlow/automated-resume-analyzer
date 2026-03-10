from __future__ import annotations

from typing import Any, NoReturn

from fastapi import HTTPException

from .responses import ErrorInfo


def build_error_detail(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ErrorInfo(code=code, message=message, details=details or {}).model_dump()


def make_http_exception(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=build_error_detail(code=code, message=message, details=details),
    )


def raise_http(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> NoReturn:
    raise make_http_exception(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    )
