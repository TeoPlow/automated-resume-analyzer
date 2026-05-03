from fastapi import APIRouter

from common.schemas.base import BaseResponse
from common.schemas.health import HealthData


def make_health_router(service_name: str) -> APIRouter:
    """Создать роутер с эндпоинтом /api/v1/health для указанного сервиса."""
    router = APIRouter(tags=["health"])

    @router.get("/api/v1/health")
    async def health() -> BaseResponse[HealthData]:
        """Проверка работоспособности сервиса."""
        return BaseResponse(data=HealthData(service=service_name))

    return router
