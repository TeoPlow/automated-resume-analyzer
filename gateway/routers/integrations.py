from typing import Annotated

from fastapi import APIRouter, Depends, Security
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from common.exceptions import AppError
from common.schemas.base import BaseResponse

from gateway.schemas.auth import (
    IntegrationKeyCreateData,
    IntegrationKeyCreateRequest,
    IntegrationKeyInfo,
    MeData,
)
from gateway.services.auth_service import AuthService


def create_router(auth_service: AuthService) -> APIRouter:
    """Создать роутер для управления интеграционными ключами."""
    router = APIRouter(prefix="/integrations/keys", tags=["integrations"])
    bearer_scheme = HTTPBearer(auto_error=False)
    api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

    async def authenticate_actor(
        bearer: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(bearer_scheme),
        ],
        api_key: Annotated[str | None, Security(api_key_scheme)],
    ) -> MeData:
        """Аутентифицировать актора по Bearer-токену или API-ключу."""
        authorization = None
        if bearer:
            authorization = f"{bearer.scheme} {bearer.credentials}"
        return await auth_service.authenticate_request(
            authorization=authorization,
            api_key=api_key,
        )

    @router.post("")
    async def create_key(
        body: IntegrationKeyCreateRequest,
        actor: MeData = Depends(authenticate_actor),
    ) -> BaseResponse[IntegrationKeyCreateData]:
        """Создать новый API-ключ для внешней интеграции."""
        _require_admin(actor)
        result = await auth_service.create_integration_key(
            body.name, body.permissions
        )
        return BaseResponse(data=result)

    @router.get("")
    async def list_keys(
        actor: MeData = Depends(authenticate_actor),
    ) -> BaseResponse[list[IntegrationKeyInfo]]:
        """Получить список всех API-ключей."""
        _require_admin(actor)
        keys = await auth_service.list_integration_keys()
        return BaseResponse(data=keys)

    @router.post("/{key_id}/rotate")
    async def rotate_key(
        key_id: str,
        actor: MeData = Depends(authenticate_actor),
    ) -> BaseResponse[IntegrationKeyCreateData]:
        """Ротировать ключ: отозвать старый, создать новый с тем же именем."""
        _require_admin(actor)
        result = await auth_service.rotate_integration_key(key_id)
        return BaseResponse(data=result)

    @router.delete("/{key_id}", status_code=204)
    async def revoke_key(
        key_id: str,
        actor: MeData = Depends(authenticate_actor),
    ) -> None:
        """Отозвать (деактивировать) API-ключ интеграции."""
        _require_admin(actor)
        await auth_service.revoke_integration_key(key_id)

    return router


def _require_admin(actor: MeData) -> None:
    """Проверить, что текущий пользователь имеет право integrations:manage."""
    if "integrations:manage" not in actor.permissions:
        raise AppError(
            code="forbidden",
            message="Требуются права администратора",
            status_code=403,
        )
