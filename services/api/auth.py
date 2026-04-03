import base64
import hashlib
import hmac
import importlib
import json
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated, Any, Protocol

from fastapi import Depends, Header

from libs import (
    Actor,
    IntegrationKeyCreateResponse,
    IntegrationKeyInfo,
    TokenPair,
    make_http_exception,
    raise_http,
)


JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me")
JWT_ISSUER = os.getenv("JWT_ISSUER", "resume-analyzer-api")
ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1800"))
REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", str(60 * 60 * 24 * 14)))
INTEGRATION_KEY_PREFIX = "ara_"
AUTH_REDIS_PREFIX = os.getenv("AUTH_REDIS_PREFIX", "auth")

logger = logging.getLogger(__name__)


USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "password": os.getenv("ADMIN_PASSWORD", "admin123"),
        "is_admin": True,
        "user_id": "u_admin",
    },
    "hr": {
        "password": os.getenv("HR_PASSWORD", "hr123"),
        "is_admin": False,
        "user_id": "u_hr",
    },
}


class AuthStore(Protocol):
    def set_refresh_token(self, jti: str, meta: dict[str, Any]) -> None:
        ...

    def get_refresh_token(self, jti: str) -> dict[str, Any] | None:
        ...

    def revoke_refresh_token(self, jti: str) -> bool:
        ...

    def set_integration_key(self, key_hash: str, info: dict[str, Any]) -> None:
        ...

    def get_integration_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        ...

    def get_integration_key_by_key_id(self, key_id: str) -> tuple[str, dict[str, Any]] | None:
        ...

    def list_integration_keys(self) -> list[dict[str, Any]]:
        ...

    def revoke_integration_key_by_hash(self, key_hash: str) -> bool:
        ...


def _seconds_until(expiration: datetime) -> int:
    remaining = int((expiration - datetime.now(UTC)).total_seconds())
    return max(remaining, 1)


def _serialize_refresh(meta: dict[str, Any]) -> str:
    payload = {
        "actor_id": str(meta["actor_id"]),
        "is_admin": bool(meta["is_admin"]),
        "expires_at": meta["expires_at"].isoformat(),
        "revoked": bool(meta.get("revoked", False)),
    }
    return json.dumps(payload)


def _deserialize_refresh(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    return {
        "actor_id": str(payload["actor_id"]),
        "is_admin": bool(payload["is_admin"]),
        "expires_at": datetime.fromisoformat(str(payload["expires_at"])),
        "revoked": bool(payload.get("revoked", False)),
    }


def _serialize_integration(info: dict[str, Any]) -> str:
    payload = {
        "key_id": str(info["key_id"]),
        "name": str(info["name"]),
        "created_at": info["created_at"].isoformat(),
        "revoked": bool(info.get("revoked", False)),
    }
    return json.dumps(payload)


def _deserialize_integration(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    return {
        "key_id": str(payload["key_id"]),
        "name": str(payload["name"]),
        "created_at": datetime.fromisoformat(str(payload["created_at"])),
        "revoked": bool(payload.get("revoked", False)),
    }


class InMemoryAuthStore:
    def __init__(self) -> None:
        self._refresh_tokens: dict[str, dict[str, Any]] = {}
        self._integration_keys: dict[str, dict[str, Any]] = {}
        self._integration_by_id: dict[str, str] = {}

    def set_refresh_token(self, jti: str, meta: dict[str, Any]) -> None:
        self._refresh_tokens[jti] = meta

    def get_refresh_token(self, jti: str) -> dict[str, Any] | None:
        return self._refresh_tokens.get(jti)

    def revoke_refresh_token(self, jti: str) -> bool:
        meta = self._refresh_tokens.get(jti)
        if not meta:
            return False
        meta["revoked"] = True
        return True

    def set_integration_key(self, key_hash: str, info: dict[str, Any]) -> None:
        self._integration_keys[key_hash] = info
        self._integration_by_id[str(info["key_id"])] = key_hash

    def get_integration_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        return self._integration_keys.get(key_hash)

    def get_integration_key_by_key_id(self, key_id: str) -> tuple[str, dict[str, Any]] | None:
        key_hash = self._integration_by_id.get(key_id)
        if not key_hash:
            return None
        info = self._integration_keys.get(key_hash)
        if not info:
            return None
        return key_hash, info

    def list_integration_keys(self) -> list[dict[str, Any]]:
        return list(self._integration_keys.values())

    def revoke_integration_key_by_hash(self, key_hash: str) -> bool:
        info = self._integration_keys.get(key_hash)
        if not info:
            return False
        info["revoked"] = True
        return True


class RedisAuthStore:
    def __init__(self) -> None:
        redis_module = importlib.import_module("redis")

        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_AUTH_DB", "0"))
        password = os.getenv("REDIS_PASSWORD") or None

        self.client = redis_module.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
        )
        self.client.ping()

    @staticmethod
    def _refresh_key(jti: str) -> str:
        return f"{AUTH_REDIS_PREFIX}:refresh:{jti}"

    @staticmethod
    def _integration_hash_key(key_hash: str) -> str:
        return f"{AUTH_REDIS_PREFIX}:integration:{key_hash}"

    @staticmethod
    def _integration_id_key(key_id: str) -> str:
        return f"{AUTH_REDIS_PREFIX}:integration:key-id:{key_id}"

    @staticmethod
    def _integration_set_key() -> str:
        return f"{AUTH_REDIS_PREFIX}:integration:all"

    def set_refresh_token(self, jti: str, meta: dict[str, Any]) -> None:
        self.client.set(self._refresh_key(jti), _serialize_refresh(meta), ex=_seconds_until(meta["expires_at"]))

    def get_refresh_token(self, jti: str) -> dict[str, Any] | None:
        raw = self.client.get(self._refresh_key(jti))
        if raw is None:
            return None
        return _deserialize_refresh(raw)

    def revoke_refresh_token(self, jti: str) -> bool:
        key = self._refresh_key(jti)
        raw = self.client.get(key)
        if raw is None:
            return False

        meta = _deserialize_refresh(raw)
        meta["revoked"] = True
        self.client.set(key, _serialize_refresh(meta), ex=_seconds_until(meta["expires_at"]))
        return True

    def set_integration_key(self, key_hash: str, info: dict[str, Any]) -> None:
        self.client.set(self._integration_hash_key(key_hash), _serialize_integration(info))
        self.client.set(self._integration_id_key(str(info["key_id"])), key_hash)
        self.client.sadd(self._integration_set_key(), key_hash)

    def get_integration_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        raw = self.client.get(self._integration_hash_key(key_hash))
        if raw is None:
            return None
        return _deserialize_integration(raw)

    def get_integration_key_by_key_id(self, key_id: str) -> tuple[str, dict[str, Any]] | None:
        key_hash = self.client.get(self._integration_id_key(key_id))
        if key_hash is None:
            return None

        info = self.get_integration_key_by_hash(key_hash)
        if info is None:
            return None
        return key_hash, info

    def list_integration_keys(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for key_hash in self.client.smembers(self._integration_set_key()):
            info = self.get_integration_key_by_hash(str(key_hash))
            if info is not None:
                results.append(info)
        return results

    def revoke_integration_key_by_hash(self, key_hash: str) -> bool:
        info = self.get_integration_key_by_hash(key_hash)
        if info is None:
            return False
        info["revoked"] = True
        self.client.set(self._integration_hash_key(key_hash), _serialize_integration(info))
        return True


def _create_auth_store() -> AuthStore:
    backend = os.getenv("AUTH_STORE_BACKEND", "redis").lower()
    if backend == "memory":
        logger.warning("AUTH_STORE_BACKEND=memory is enabled; state will not persist across restarts")
        return InMemoryAuthStore()

    try:
        return RedisAuthStore()
    except Exception as exc:
        logger.warning("Redis auth store unavailable (%s); falling back to in-memory store", exc)
        return InMemoryAuthStore()


auth_store = _create_auth_store()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode((encoded + padding).encode("ascii"))


def _sign_token(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64url_encode(signature)}"


def _decode_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Invalid token format")

    header_part, payload_part, signature_part = parts
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _b64url_decode(signature_part)
    except Exception as exc:
        raise make_http_exception(
            status_code=HTTPStatus.UNAUTHORIZED,
            code="invalid_token",
            message="Invalid token signature",
        ) from exc

    if not hmac.compare_digest(actual_sig, expected_sig):
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Token signature mismatch")

    payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    now_ts = int(datetime.now(UTC).timestamp())
    if payload.get("iss") != JWT_ISSUER:
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Token issuer mismatch")
    if now_ts >= int(payload.get("exp", 0)):
        raise_http(HTTPStatus.UNAUTHORIZED, "token_expired", "Token has expired")
    return payload


def _issue_tokens(actor_id: str, is_admin: bool) -> TokenPair:
    now = datetime.now(UTC)
    access_exp = now + timedelta(seconds=ACCESS_TTL_SECONDS)
    refresh_exp = now + timedelta(seconds=REFRESH_TTL_SECONDS)

    access_payload = {
        "iss": JWT_ISSUER,
        "sub": actor_id,
        "is_admin": is_admin,
        "type": "access",
        "exp": int(access_exp.timestamp()),
        "iat": int(now.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    refresh_jti = uuid.uuid4().hex
    refresh_payload = {
        "iss": JWT_ISSUER,
        "sub": actor_id,
        "is_admin": is_admin,
        "type": "refresh",
        "exp": int(refresh_exp.timestamp()),
        "iat": int(now.timestamp()),
        "jti": refresh_jti,
    }
    auth_store.set_refresh_token(refresh_jti, {
        "actor_id": actor_id,
        "is_admin": is_admin,
        "expires_at": refresh_exp,
        "revoked": False,
    })
    return TokenPair(
        access_token=_sign_token(access_payload),
        refresh_token=_sign_token(refresh_payload),
        expires_in=ACCESS_TTL_SECONDS,
    )


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _build_actor_from_access_token(access_token: str) -> Actor:
    payload = _decode_token(access_token)
    if payload.get("type") != "access":
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Access token required")
    return Actor(
        actor_id=str(payload["sub"]),
        actor_type="hr",
        is_admin=bool(payload.get("is_admin", False)),
    )


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value


def authenticate(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Actor:
    bearer = _extract_bearer_token(authorization)
    if bearer:
        return _build_actor_from_access_token(bearer)

    if x_api_key:
        key_hash = _hash_api_key(x_api_key)
        key_info = auth_store.get_integration_key_by_hash(key_hash)
        if key_info and not key_info["revoked"]:
            return Actor(actor_id=str(key_info["key_id"]), actor_type="integration", is_admin=False)

    raise_http(HTTPStatus.UNAUTHORIZED, "unauthorized", "Missing or invalid credentials")


def require_admin(actor: Annotated[Actor, Depends(authenticate)]) -> Actor:
    if not actor.is_admin:
        raise_http(HTTPStatus.FORBIDDEN, "forbidden", "Admin role required")
    return actor


def login_user(username: str, password: str) -> TokenPair:
    user_record = USERS.get(username)
    if not user_record or not secrets.compare_digest(str(user_record["password"]), password):
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_credentials", "Invalid username or password")
    return _issue_tokens(actor_id=str(user_record["user_id"]), is_admin=bool(user_record["is_admin"]))


def refresh_user_tokens(refresh_token: str) -> TokenPair:
    refresh_payload = _decode_token(refresh_token)
    if refresh_payload.get("type") != "refresh":
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Refresh token required")
    jti = str(refresh_payload.get("jti", ""))
    refresh_meta = auth_store.get_refresh_token(jti)
    if not refresh_meta or refresh_meta["revoked"]:
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Refresh token is revoked or unknown")
    if datetime.now(UTC) >= refresh_meta["expires_at"]:
        raise_http(HTTPStatus.UNAUTHORIZED, "token_expired", "Refresh token has expired")

    auth_store.revoke_refresh_token(jti)
    return _issue_tokens(actor_id=str(refresh_meta["actor_id"]), is_admin=bool(refresh_meta["is_admin"]))


def logout_user(refresh_token: str) -> None:
    refresh_payload = _decode_token(refresh_token)
    if refresh_payload.get("type") != "refresh":
        raise_http(HTTPStatus.BAD_REQUEST, "invalid_token", "Refresh token required")
    jti = str(refresh_payload.get("jti", ""))
    auth_store.revoke_refresh_token(jti)


def create_integration_api_key(name: str) -> IntegrationKeyCreateResponse:
    raw_key = f"{INTEGRATION_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    created_at = datetime.now(UTC)
    key_id = uuid.uuid4().hex
    auth_store.set_integration_key(key_hash, {
        "key_id": key_id,
        "name": name,
        "created_at": created_at,
        "revoked": False,
    })
    return IntegrationKeyCreateResponse(
        key_id=key_id,
        name=name,
        api_key=raw_key,
        created_at=created_at,
    )


def list_integration_api_keys() -> list[IntegrationKeyInfo]:
    infos = sorted(auth_store.list_integration_keys(), key=lambda item: item["created_at"], reverse=True)
    return [
        IntegrationKeyInfo(
            key_id=str(info["key_id"]),
            name=str(info["name"]),
            created_at=info["created_at"],
            revoked=bool(info["revoked"]),
        )
        for info in infos
    ]


def rotate_integration_api_key(key_id: str) -> IntegrationKeyCreateResponse:
    found = auth_store.get_integration_key_by_key_id(key_id)
    if not found:
        raise_http(HTTPStatus.NOT_FOUND, "key_not_found", "Integration key not found")
    found_hash, found_info = found

    auth_store.revoke_integration_key_by_hash(found_hash)
    raw_key = f"{INTEGRATION_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    new_hash = _hash_api_key(raw_key)
    created_at = datetime.now(UTC)
    new_key_id = uuid.uuid4().hex
    auth_store.set_integration_key(new_hash, {
        "key_id": new_key_id,
        "name": found_info["name"],
        "created_at": created_at,
        "revoked": False,
    })
    return IntegrationKeyCreateResponse(
        key_id=new_key_id,
        name=str(found_info["name"]),
        api_key=raw_key,
        created_at=created_at,
    )


def revoke_integration_api_key(key_id: str) -> None:
    found = auth_store.get_integration_key_by_key_id(key_id)
    if found:
        key_hash, _ = found
        auth_store.revoke_integration_key_by_hash(key_hash)
        return
    raise_http(HTTPStatus.NOT_FOUND, "key_not_found", "Integration key not found")
