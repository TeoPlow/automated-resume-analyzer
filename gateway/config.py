import os


class GatewayConfig:
    """Настройки Gateway, загружаемые из переменных окружения."""

    # JWT
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET", "super-secret-jwt-key-change-in-production"
    )
    JWT_ACCESS_TTL: int = int(os.getenv("JWT_ACCESS_TTL", "3600"))
    JWT_REFRESH_TTL: int = int(os.getenv("JWT_REFRESH_TTL", "86400"))

    # Rate limiting (скользящее окно)
    RATE_LIMIT_MAX: int = int(os.getenv("RATE_LIMIT_MAX", "120"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # Пользователи (для MVP — из env, в продакшене — из БД)
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    HR_USERNAME: str = os.getenv("HR_USERNAME", "hr")
    HR_PASSWORD: str = os.getenv("HR_PASSWORD", "hr123")

    # Downstream-сервисы
    PROFILE_URL: str = os.getenv("PROFILE_SERVICE_URL", "http://profile:8000")
    VACANCY_URL: str = os.getenv("VACANCY_SERVICE_URL", "http://vacancy:8000")
    MATCHING_URL: str = os.getenv("MATCHING_SERVICE_URL", "http://matching:8000")
    SEARCH_URL: str = os.getenv("SEARCH_SERVICE_URL", "http://search:8000")

    # Межсервисный токен
    INTERNAL_TOKEN: str = os.getenv("INTERNAL_TOKEN", "internal-secret-token")

    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
