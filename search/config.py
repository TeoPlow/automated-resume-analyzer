import os


class SearchConfig:
    """Настройки Search-сервиса."""

    # PostgreSQL (read-only доступ ко всем схемам)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:app_password@postgres:5432/resume_analyzer",
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # Значения по умолчанию для пагинации
    DEFAULT_LIMIT: int = int(os.getenv("DEFAULT_LIMIT", "20"))
    MAX_LIMIT: int = int(os.getenv("MAX_LIMIT", "100"))

    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
