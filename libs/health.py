from fastapi import FastAPI

from .responses import HealthResponse


def install_health_endpoint(app: FastAPI) -> None:
    """Проверка здоровья сервисов"""
    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse.for_service(app.title)