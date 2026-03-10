import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated, Any

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


# TODO: replace with DB-backed users.
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


refresh_tokens_store: dict[str, dict[str, Any]] = {}
integration_keys_store: dict[str, dict[str, Any]] = {}


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
    refresh_tokens_store[refresh_jti] = {
        "actor_id": actor_id,
        "is_admin": is_admin,
        "expires_at": refresh_exp,
        "revoked": False,
    }
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
        key_info = integration_keys_store.get(key_hash)
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
    refresh_meta = refresh_tokens_store.get(jti)
    if not refresh_meta or refresh_meta["revoked"]:
        raise_http(HTTPStatus.UNAUTHORIZED, "invalid_token", "Refresh token is revoked or unknown")
    if datetime.now(UTC) >= refresh_meta["expires_at"]:
        raise_http(HTTPStatus.UNAUTHORIZED, "token_expired", "Refresh token has expired")

    refresh_meta["revoked"] = True
    return _issue_tokens(actor_id=str(refresh_meta["actor_id"]), is_admin=bool(refresh_meta["is_admin"]))


def logout_user(refresh_token: str) -> None:
    refresh_payload = _decode_token(refresh_token)
    if refresh_payload.get("type") != "refresh":
        raise_http(HTTPStatus.BAD_REQUEST, "invalid_token", "Refresh token required")
    jti = str(refresh_payload.get("jti", ""))
    if jti in refresh_tokens_store:
        refresh_tokens_store[jti]["revoked"] = True


def create_integration_api_key(name: str) -> IntegrationKeyCreateResponse:
    raw_key = f"{INTEGRATION_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    created_at = datetime.now(UTC)
    key_id = uuid.uuid4().hex
    integration_keys_store[key_hash] = {
        "key_id": key_id,
        "name": name,
        "created_at": created_at,
        "revoked": False,
    }
    return IntegrationKeyCreateResponse(
        key_id=key_id,
        name=name,
        api_key=raw_key,
        created_at=created_at,
    )


def list_integration_api_keys() -> list[IntegrationKeyInfo]:
    return [
        IntegrationKeyInfo(
            key_id=str(info["key_id"]),
            name=str(info["name"]),
            created_at=info["created_at"],
            revoked=bool(info["revoked"]),
        )
        for info in integration_keys_store.values()
    ]


def rotate_integration_api_key(key_id: str) -> IntegrationKeyCreateResponse:
    found_hash = None
    found_info = None
    for key_hash, info in integration_keys_store.items():
        if info["key_id"] == key_id:
            found_hash = key_hash
            found_info = info
            break
    if not found_hash or not found_info:
        raise_http(HTTPStatus.NOT_FOUND, "key_not_found", "Integration key not found")

    integration_keys_store[found_hash]["revoked"] = True
    raw_key = f"{INTEGRATION_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    new_hash = _hash_api_key(raw_key)
    created_at = datetime.now(UTC)
    new_key_id = uuid.uuid4().hex
    integration_keys_store[new_hash] = {
        "key_id": new_key_id,
        "name": found_info["name"],
        "created_at": created_at,
        "revoked": False,
    }
    return IntegrationKeyCreateResponse(
        key_id=new_key_id,
        name=str(found_info["name"]),
        api_key=raw_key,
        created_at=created_at,
    )


def revoke_integration_api_key(key_id: str) -> None:
    for key_hash, info in integration_keys_store.items():
        if info["key_id"] == key_id:
            integration_keys_store[key_hash]["revoked"] = True
            return
    raise_http(HTTPStatus.NOT_FOUND, "key_not_found", "Integration key not found")
