from typing import Any

from pydantic import BaseModel

from .base import BaseResponse


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseResponse[dict[str, Any]]):
    error: ErrorInfo
