from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    status: Literal["ok", "error"]
    data: T | None = None
