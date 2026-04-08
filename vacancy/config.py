import os


class VacancyConfig:
    """Настройки Vacancy-сервиса."""

    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:app_password@postgres:5432/resume_analyzer",
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # RabbitMQ
    RABBITMQ_URL: str = os.getenv(
        "RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"
    )
    EXCHANGE_NAME: str = os.getenv("EXCHANGE_NAME", "ara.events")
    DLX_NAME: str = os.getenv("DLX_NAME", "ara.events.dlx")

    # Межсервисный токен
    INTERNAL_TOKEN: str = os.getenv("INTERNAL_TOKEN", "internal-secret-token")

    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
