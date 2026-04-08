import base64
import hashlib
import hmac
import json
import time
import uuid

from common.exceptions import AppError


class JwtService:
    """Создание и валидация JWT-токенов с алгоритмом HS256."""

    def __init__(self, secret: str, access_ttl: int, refresh_ttl: int) -> None:
        self._secret = secret.encode()
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl

    def create_access_token(
        self,
        actor_id: str,
        actor_type: str,
        permissions: list[str],
    ) -> str:
        """Создать access-токен с данными актора."""
        now = int(time.time())
        payload = {
            "sub": actor_id,
            "type": "access",
            "actor_type": actor_type,
            "permissions": permissions,
            "iat": now,
            "exp": now + self._access_ttl,
        }
        return self._encode(payload)

    def create_refresh_token(self, actor_id: str) -> tuple[str, str]:
        """Создать refresh-токен. Возвращает кортеж (токен, jti)."""
        now = int(time.time())
        jti = str(uuid.uuid4())
        payload = {
            "sub": actor_id,
            "type": "refresh",
            "jti": jti,
            "iat": now,
            "exp": now + self._refresh_ttl,
        }
        return self._encode(payload), jti

    def decode(self, token: str) -> dict:
        """Декодировать и валидировать JWT-токен. Выбрасывает AppError."""
        parts = token.split(".")
        if len(parts) != 3:
            raise AppError(
                code="invalid_token",
                message="Неверный формат токена",
                status_code=401,
            )

        header_seg, payload_seg, signature_seg = parts
        expected_sig = self._sign(f"{header_seg}.{payload_seg}")

        if not hmac.compare_digest(signature_seg, expected_sig):
            raise AppError(
                code="invalid_token",
                message="Неверная подпись токена",
                status_code=401,
            )

        payload = json.loads(self._base64url_decode(payload_seg))

        if payload.get("exp", 0) < int(time.time()):
            raise AppError(
                code="token_expired",
                message="Токен истёк",
                status_code=401,
            )

        return payload


    def _encode(self, payload: dict) -> str:
        """Собрать JWT-строку из payload."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_seg = self._base64url_encode(json.dumps(header).encode())
        payload_seg = self._base64url_encode(json.dumps(payload).encode())
        signature = self._sign(f"{header_seg}.{payload_seg}")
        return f"{header_seg}.{payload_seg}.{signature}"

    def _sign(self, data: str) -> str:
        """Создать HMAC-SHA256 подпись и вернуть base64url-строку."""
        sig = hmac.new(self._secret, data.encode(), hashlib.sha256).digest()
        return self._base64url_encode(sig)

    def _base64url_encode(self, data: bytes) -> str:
        """Base64url кодирование без паддинга (RFC 7515)."""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _base64url_decode(self, data: str) -> bytes:
        """Base64url декодирование с восстановлением паддинга."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)
