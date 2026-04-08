from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Детали ошибки."""

    code: str
    message: str
    details: dict = {}
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Стандартный ответ с ошибкой."""

    status: str = "error"
    error: ErrorDetail
