from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationData(BaseModel):
    """Данные пагинации в ответе."""

    limit: int
    offset: int
    total: int


class BaseResponse(BaseModel, Generic[T]):
    """Стандартная обёртка для успешного ответа."""

    status: str = "ok"
    data: T | None = None
    pagination: PaginationData | None = None
