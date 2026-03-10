from typing import Self

from pydantic import BaseModel

from .base import BaseResponse


class HealthInfo(BaseModel):
    service: str


class HealthResponse(BaseResponse[HealthInfo]):
    @classmethod
    def for_service(cls, service_name: str) -> Self:
        return cls(status="ok", data=HealthInfo(service=service_name))
