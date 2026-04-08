from fastapi import Request
from pydantic import BaseModel

from common.exceptions import AppError


class Actor(BaseModel):
    """Представление аутентифицированного актора."""

    actor_id: str
    actor_type: str
    permissions: list[str] = []


def extract_actor(request: Request) -> Actor:
    """Извлечь данные актора из X-* заголовков, установленных Gateway."""
    actor_id = request.headers.get("x-actor-id")
    if not actor_id:
        raise AppError(
            code="unauthorized",
            message="Отсутствуют заголовки авторизации",
            status_code=401,
        )
    return Actor(
        actor_id=actor_id,
        actor_type=request.headers.get("x-actor-type", "hr"),
        permissions=_parse_permissions(request.headers.get("x-permissions", "")),
    )


def require_permission(actor: Actor, permission: str) -> None:
    """Проверить наличие разрешения у актора. Выбрасывает 403 при отсутствии."""
    if permission not in actor.permissions:
        raise AppError(
            code="forbidden",
            message=f"Требуется разрешение: {permission}",
            status_code=403,
        )


def require_internal(request: Request, expected_token: str) -> None:
    """Проверить X-Internal-Token для межсервисных вызовов."""
    token = request.headers.get("x-internal-token", "")
    if token != expected_token:
        raise AppError(
            code="unauthorized",
            message="Неверный внутренний токен",
            status_code=401,
        )


def _parse_permissions(raw: str) -> list[str]:
    """Разобрать строку разрешений, разделённых запятой, в список."""
    return [p.strip() for p in raw.split(",") if p.strip()]
