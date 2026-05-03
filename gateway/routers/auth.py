from typing import Annotated

from fastapi import APIRouter, Depends, Security
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from common.schemas.base import BaseResponse

from gateway.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeData,
    RefreshRequest,
    TokenPairData,
)
from gateway.services.auth_service import AuthService


def create_router(auth_service: AuthService) -> APIRouter:
    """Создать роутер для эндпоинтов аутентификации"""
    router = APIRouter(tags=["auth"])
    bearer_scheme = HTTPBearer(auto_error=False)
    api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

    async def authenticate_actor(
        bearer: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(bearer_scheme),
        ],
        api_key: Annotated[str | None, Security(api_key_scheme)],
    ) -> MeData:
        """Аутентифицировать актора по Bearer-токену или API-ключу"""
        authorization = None
        if bearer:
            authorization = f"{bearer.scheme} {bearer.credentials}"
        return await auth_service.authenticate_request(
            authorization=authorization,
            api_key=api_key,
        )

    @router.post("/auth/login")
    async def login(body: LoginRequest) -> BaseResponse[TokenPairData]:
        """Аутентификация HR-пользователя, выдача пары токенов"""
        result = await auth_service.login(body.username, body.password)
        return BaseResponse(data=result)

    @router.post("/auth/refresh")
    async def refresh(body: RefreshRequest) -> BaseResponse[TokenPairData]:
        """Обновление access-токена по refresh-токену"""
        result = await auth_service.refresh(body.refresh_token)
        return BaseResponse(data=result)

    @router.post("/auth/logout", status_code=204)
    async def logout(body: LogoutRequest) -> None:
        """Отзыв refresh-токена"""
        await auth_service.logout(body.refresh_token)

    @router.get("/me")
    async def me(
        actor: MeData = Depends(authenticate_actor),
    ) -> BaseResponse[MeData]:
        """Получение данных текущего аутентифицированного пользователя"""
        return BaseResponse(data=actor)

    return router
