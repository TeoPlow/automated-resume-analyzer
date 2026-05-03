import os


class MatchingConfig:
    """Настройки Matching-сервиса."""

    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:app_password@postgres:5432/resume_analyzer",
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # RabbitMQ
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    EXCHANGE_NAME: str = os.getenv("EXCHANGE_NAME", "ara.events")
    DLX_NAME: str = os.getenv("DLX_NAME", "ara.events.dlx")

    # Межсервисные вызовы
    PROFILE_URL: str = os.getenv("PROFILE_SERVICE_URL", "http://profile:8000")
    VACANCY_URL: str = os.getenv("VACANCY_SERVICE_URL", "http://vacancy:8000")
    INTERNAL_TOKEN: str = os.getenv("INTERNAL_TOKEN", "internal-secret-token")

    # Embedding-модель (sentence-transformers)
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )

    # Веса по умолчанию для формулы матчинга
    DEFAULT_WEIGHT_SKILLS: float = float(os.getenv("DEFAULT_WEIGHT_SKILLS", "0.40"))
    DEFAULT_WEIGHT_EXPERIENCE: float = float(
        os.getenv("DEFAULT_WEIGHT_EXPERIENCE", "0.25")
    )
    DEFAULT_WEIGHT_GRADE: float = float(os.getenv("DEFAULT_WEIGHT_GRADE", "0.15"))
    DEFAULT_WEIGHT_LOCATION: float = float(os.getenv("DEFAULT_WEIGHT_LOCATION", "0.10"))
    DEFAULT_WEIGHT_SALARY: float = float(os.getenv("DEFAULT_WEIGHT_SALARY", "0.10"))

    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
