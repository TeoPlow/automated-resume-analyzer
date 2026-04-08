from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from starlette.responses import Response

from common.exceptions import AppError

from gateway.services.auth_service import AuthService
from gateway.services.proxy_service import ProxyService
from gateway.services.rate_limiter import SlidingWindowRateLimiter
from gateway.schemas.auth import MeData


def create_router(
    auth_service: AuthService,
    proxy_service: ProxyService,
    rate_limiter: SlidingWindowRateLimiter,
) -> APIRouter:
    """Создать catch-all роутер для проксирования в микросервисы."""
    router = APIRouter(tags=["proxy"])
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

    async def proxy_request(
        request: Request,
        service: str,
        path: str,
        actor: MeData,
    ) -> Response:
        """Проксировать запрос в сервис с проверкой лимитов и авторизации."""
        client_key = rate_limiter.extract_client_key(request)
        if not await rate_limiter.check(client_key):
            raise AppError(
                code="rate_limit_exceeded",
                message="Слишком много запросов. Повторите позже",
                status_code=429,
            )

        return await proxy_service.forward(request, service, path, actor)

    @router.api_route(
        "/{service}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def proxy_root(
        request: Request,
        service: str,
        actor: MeData = Depends(authenticate_actor),
    ) -> Response:
        """Проксировать запросы на корневой путь сервиса (/profiles, /vacancies и т.д.)."""
        return await proxy_request(request, service, "", actor)

    @router.api_route(
        "/{service}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def proxy(
        request: Request,
        service: str,
        path: str,
        actor: MeData = Depends(authenticate_actor),
    ) -> Response:
        """Проксировать запрос в соответствующий микросервис.

        Выполняет rate-limit проверку, аутентификацию и пересылку.
        """
        return await proxy_request(request, service, path, actor)

    return router
