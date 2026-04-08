import hashlib
import secrets
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from common.exceptions import AppError
from common.logger import setup_logger

from gateway.config import GatewayConfig
from gateway.models.user import HRUser, IntegrationKey
from gateway.schemas.auth import (
    IntegrationKeyCreateData,
    IntegrationKeyInfo,
    MeData,
    TokenPairData,
)
from gateway.services.jwt_service import JwtService

logger = setup_logger("gateway.auth")


class AuthStore(ABC):
    """Абстрактное хранилище данных аутентификации (Strategy pattern)."""

    @abstractmethod
    async def add_to_blacklist(self, jti: str, ttl_seconds: int) -> None:
        """Добавить JTI отозванного refresh-токена в чёрный список."""
        ...

    @abstractmethod
    async def is_blacklisted(self, jti: str) -> bool:
        """Проверить, находится ли JTI в чёрном списке."""
        ...

    @abstractmethod
    async def save_integration_key(self, key: IntegrationKey) -> None:
        """Сохранить интеграционный ключ."""
        ...

    @abstractmethod
    async def get_integration_key_by_hash(
        self, key_hash: str
    ) -> IntegrationKey | None:
        """Найти активный ключ по SHA256-хешу."""
        ...

    @abstractmethod
    async def list_integration_keys(self) -> list[IntegrationKey]:
        """Получить список всех ключей."""
        ...

    @abstractmethod
    async def delete_integration_key(self, key_id: str) -> bool:
        """Деактивировать ключ по ID. Возвращает True если ключ найден."""
        ...


class InMemoryAuthStore(AuthStore):
    """Хранилище в оперативной памяти (для разработки и тестирования)."""

    def __init__(self) -> None:
        self._blacklist: dict[str, float] = {}
        self._keys: dict[str, IntegrationKey] = {}

    async def add_to_blacklist(self, jti: str, ttl_seconds: int) -> None:
        """Добавить JTI в blacklist с временем истечения."""
        self._blacklist[jti] = time.time() + ttl_seconds

    async def is_blacklisted(self, jti: str) -> bool:
        """Проверить наличие JTI в blacklist с учётом TTL."""
        expires = self._blacklist.get(jti)
        if expires is None:
            return False
        if time.time() > expires:
            del self._blacklist[jti]
            return False
        return True

    async def save_integration_key(self, key: IntegrationKey) -> None:
        """Сохранить ключ в память."""
        self._keys[key.key_id] = key

    async def get_integration_key_by_hash(
        self, key_hash: str
    ) -> IntegrationKey | None:
        """Найти активный ключ по хешу."""
        for key in self._keys.values():
            if key.key_hash == key_hash and key.is_active:
                return key
        return None

    async def list_integration_keys(self) -> list[IntegrationKey]:
        """Получить все ключи."""
        return list(self._keys.values())

    async def delete_integration_key(self, key_id: str) -> bool:
        """Деактивировать ключ."""
        key = self._keys.get(key_id)
        if not key:
            return False
        key.is_active = False
        return True


class AuthService:
    """Главный сервис аутентификации Gateway.

    Отвечает за:
    - Логин/логаут HR-пользователей (JWT)
    - Аутентификацию по Bearer-токену и API-ключу
    - Управление интеграционными ключами
    """

    def __init__(
        self,
        config: GatewayConfig,
        store: AuthStore,
        jwt: JwtService,
    ) -> None:
        self._config = config
        self._store = store
        self._jwt = jwt
        self._users = self._build_user_registry()

    async def login(self, username: str, password: str) -> TokenPairData:
        """Аутентифицировать пользователя и выдать пару токенов."""
        user = self._users.get(username)
        if not user or user.password != password:
            raise AppError(
                code="invalid_credentials",
                message="Неверное имя пользователя или пароль",
                status_code=401,
            )

        logger.info("Успешный вход: %s", username)
        return self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPairData:
        """Обновить пару токенов по refresh-токену."""
        payload = self._jwt.decode(refresh_token)
        if payload.get("type") != "refresh":
            raise AppError(
                code="invalid_token",
                message="Ожидается refresh-токен",
                status_code=401,
            )

        jti = payload.get("jti", "")
        if await self._store.is_blacklisted(jti):
            raise AppError(
                code="token_revoked",
                message="Токен отозван",
                status_code=401,
            )

        await self._store.add_to_blacklist(jti, self._config.JWT_REFRESH_TTL)

        user = self._users.get(payload["sub"])
        if not user:
            raise AppError(
                code="user_not_found",
                message="Пользователь не найден",
                status_code=401,
            )

        logger.info("Обновление токена: %s", user.username)
        return self._issue_tokens(user)

    async def logout(self, refresh_token: str) -> None:
        """Отозвать refresh-токен, добавив его JTI в blacklist."""
        try:
            payload = self._jwt.decode(refresh_token)
            jti = payload.get("jti", "")
            if jti:
                await self._store.add_to_blacklist(
                    jti, self._config.JWT_REFRESH_TTL
                )
                logger.info("Выход: токен %s отозван", jti[:8])
        except AppError:
            pass

    async def authenticate_request(
        self,
        authorization: str | None,
        api_key: str | None,
    ) -> MeData:
        """Определить актора по Bearer-токену или API-ключу."""
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            payload = self._jwt.decode(token)
            if payload.get("type") != "access":
                raise AppError(
                    code="invalid_token",
                    message="Ожидается access-токен",
                    status_code=401,
                )
            return MeData(
                actor_id=payload["sub"],
                actor_type=payload.get("actor_type", "hr"),
                permissions=payload.get("permissions", []),
            )

        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            integration = await self._store.get_integration_key_by_hash(
                key_hash
            )
            if not integration:
                raise AppError(
                    code="invalid_api_key",
                    message="Неверный API-ключ",
                    status_code=401,
                )
            return MeData(
                actor_id=f"integration:{integration.key_id}",
                actor_type="integration",
                permissions=integration.permissions,
            )

        raise AppError(
            code="unauthorized",
            message="Требуется Bearer-токен или API-ключ",
            status_code=401,
        )

    async def create_integration_key(
        self,
        name: str,
        permissions: list[str],
    ) -> IntegrationKeyCreateData:
        """Создать новый API-ключ для интеграции."""
        raw_key = secrets.token_urlsafe(32)
        key = IntegrationKey(
            key_id=secrets.token_hex(8),
            name=name,
            key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
            permissions=permissions,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._store.save_integration_key(key)
        logger.info("Создан ключ интеграции: %s (%s)", key.name, key.key_id)

        return IntegrationKeyCreateData(
            key_id=key.key_id,
            name=key.name,
            api_key=raw_key,
            permissions=key.permissions,
            created_at=key.created_at,
        )

    async def list_integration_keys(self) -> list[IntegrationKeyInfo]:
        """Получить список всех интеграционных ключей."""
        keys = await self._store.list_integration_keys()
        return [
            IntegrationKeyInfo(
                key_id=k.key_id,
                name=k.name,
                permissions=k.permissions,
                created_at=k.created_at,
                is_active=k.is_active,
            )
            for k in keys
        ]

    async def rotate_integration_key(
        self, key_id: str
    ) -> IntegrationKeyCreateData:
        """Ротировать ключ: деактивировать старый, создать новый с тем же именем."""
        keys = await self._store.list_integration_keys()
        old_key = next((k for k in keys if k.key_id == key_id), None)
        if not old_key:
            raise AppError(
                code="key_not_found",
                message="Ключ не найден",
                status_code=404,
            )

        await self._store.delete_integration_key(key_id)
        return await self.create_integration_key(
            old_key.name, old_key.permissions
        )

    async def revoke_integration_key(self, key_id: str) -> None:
        """Отозвать (деактивировать) интеграционный ключ."""
        deleted = await self._store.delete_integration_key(key_id)
        if not deleted:
            raise AppError(
                code="key_not_found",
                message="Ключ не найден",
                status_code=404,
            )
        logger.info("Ключ отозван: %s", key_id)

    # --- Приватные методы ---

    def _build_user_registry(self) -> dict[str, HRUser]:
        """Создать реестр пользователей из конфигурации."""
        all_permissions = [
            "resumes:upload",
            "candidates:read",
            "candidates:write",
            "vacancies:read",
            "vacancies:write",
            "matching:run",
            "matching:read",
            "search:use",
            "integrations:manage",
        ]
        hr_permissions = [
            p for p in all_permissions if p != "integrations:manage"
        ]

        return {
            self._config.ADMIN_USERNAME: HRUser(
                username=self._config.ADMIN_USERNAME,
                password=self._config.ADMIN_PASSWORD,
                is_admin=True,
                permissions=all_permissions,
            ),
            self._config.HR_USERNAME: HRUser(
                username=self._config.HR_USERNAME,
                password=self._config.HR_PASSWORD,
                permissions=hr_permissions,
            ),
        }

    def _issue_tokens(self, user: HRUser) -> TokenPairData:
        """Выпустить пару access + refresh токенов для пользователя."""
        access = self._jwt.create_access_token(
            actor_id=user.username,
            actor_type=user.actor_type,
            permissions=user.permissions,
        )
        refresh, _ = self._jwt.create_refresh_token(actor_id=user.username)
        return TokenPairData(access_token=access, refresh_token=refresh)
