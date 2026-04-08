from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Запрос на вход в систему."""

    username: str
    password: str


class RefreshRequest(BaseModel):
    """Запрос на обновление access-токена."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Запрос на выход (отзыв refresh-токена)."""

    refresh_token: str


class TokenPairData(BaseModel):
    """Пара access + refresh токенов."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeData(BaseModel):
    """Данные текущего аутентифицированного пользователя."""

    actor_id: str
    actor_type: str
    permissions: list[str]


class IntegrationKeyCreateRequest(BaseModel):
    """Запрос на создание API-ключа для интеграции."""

    name: str
    permissions: list[str] = ["resumes:upload"]


class IntegrationKeyInfo(BaseModel):
    """Информация о ключе интеграции (без секрета)."""

    key_id: str
    name: str
    permissions: list[str]
    created_at: str
    is_active: bool


class IntegrationKeyCreateData(BaseModel):
    """Результат создания ключа (секрет показывается один раз)."""

    key_id: str
    name: str
    api_key: str
    permissions: list[str]
    created_at: str
