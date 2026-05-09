import os


class MatchingConfig:
    """Настройки Matching-сервиса"""

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

    # Параметры скоринга (пороговые значения и дефолтные баллы)
    SKILL_SIMILARITY_THRESHOLD: float = float(
        os.getenv("SKILL_SIMILARITY_THRESHOLD", "0.6")
    )

    DEFAULT_EXPERIENCE_UNKNOWN_SCORE: float = float(
        os.getenv("DEFAULT_EXPERIENCE_UNKNOWN_SCORE", "50.0")
    )
    DEFAULT_NO_EXPERIENCE_REQUIREMENTS_SCORE: float = float(
        os.getenv("DEFAULT_NO_EXPERIENCE_REQUIREMENTS_SCORE", "80.0")
    )

    DEFAULT_GRADE_UNKNOWN_SCORE: float = float(
        os.getenv("DEFAULT_GRADE_UNKNOWN_SCORE", "50.0")
    )
    DEFAULT_GRADE_VACANCY_UNKNOWN_SCORE: float = float(
        os.getenv("DEFAULT_GRADE_VACANCY_UNKNOWN_SCORE", "80.0")
    )
    GRADE_DISTANCE_PENALTY_STEP: float = float(
        os.getenv("GRADE_DISTANCE_PENALTY_STEP", "30.0")
    )

    LOCATION_MATCH_SCORE: float = float(os.getenv("LOCATION_MATCH_SCORE", "100.0"))
    LOCATION_MISSING_CANDIDATE_SCORE: float = float(
        os.getenv("LOCATION_MISSING_CANDIDATE_SCORE", "50.0")
    )
    LOCATION_DIFFER_SCORE: float = float(os.getenv("LOCATION_DIFFER_SCORE", "30.0"))

    DEFAULT_SALARY_UNKNOWN_SCORE: float = float(
        os.getenv("DEFAULT_SALARY_UNKNOWN_SCORE", "70.0")
    )
    SALARY_NO_RANGE_SCORE: float = float(os.getenv("SALARY_NO_RANGE_SCORE", "80.0"))
    SALARY_WITHIN_SCORE: float = float(os.getenv("SALARY_WITHIN_SCORE", "100.0"))
    SALARY_BELOW_SCORE: float = float(os.getenv("SALARY_BELOW_SCORE", "90.0"))
    SALARY_OVERSHOOT_SCALE: float = float(os.getenv("SALARY_OVERSHOOT_SCALE", "100.0"))
