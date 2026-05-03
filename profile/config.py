import os


class ProfileConfig:
    """Настройки Profile-сервиса."""

    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:app_password@postgres:5432/resume_analyzer",
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # MinIO / S3
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minio")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minio123")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "resumes-raw")
    MINIO_USE_SSL: bool = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

    # Ollama (LLM)
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5:7b")
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # RabbitMQ
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    EXCHANGE_NAME: str = os.getenv("EXCHANGE_NAME", "ara.events")
    DLX_NAME: str = os.getenv("DLX_NAME", "ara.events.dlx")

    # Межсервисный токен
    INTERNAL_TOKEN: str = os.getenv("INTERNAL_TOKEN", "internal-secret-token")

    # Загрузка файлов
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(10 * 1024 * 1024)))
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "docx", "doc", "txt"]

    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
