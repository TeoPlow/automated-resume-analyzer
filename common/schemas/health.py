from pydantic import BaseModel


class HealthData(BaseModel):
    """Данные о здоровье сервиса."""

    service: str
    status: str = "healthy"
    version: str = "1.0.0"
