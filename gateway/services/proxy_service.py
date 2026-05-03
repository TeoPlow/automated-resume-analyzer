import httpx
from starlette.requests import Request
from starlette.responses import Response

from common.exceptions import AppError
from common.logger import setup_logger

from gateway.config import GatewayConfig
from gateway.schemas.auth import MeData

logger = setup_logger("gateway.proxy")

HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


class ProxyService:
    """Проксирует HTTP-запросы во внутренние микросервисы.

    Маппинг URL-префиксов на сервисы:
    - /profiles/* → Profile service
    - /vacancies/* → Vacancy service
    - /matching/* → Matching service
    - /search/* → Search service
    """

    SERVICE_MAP: dict[str, str] = {
        "profiles": "profile",
        "vacancies": "vacancy",
        "matching": "matching",
        "search": "search",
    }

    def __init__(self, config: GatewayConfig) -> None:
        self._urls: dict[str, str] = {
            "profile": config.PROFILE_URL,
            "vacancy": config.VACANCY_URL,
            "matching": config.MATCHING_URL,
            "search": config.SEARCH_URL,
        }
        self._internal_token = config.INTERNAL_TOKEN
        self._client = httpx.AsyncClient(timeout=30.0)

    async def forward(
        self,
        request: Request,
        service_key: str,
        path: str,
        actor: MeData,
    ) -> Response:
        """Переслать запрос в downstream-сервис с обогащением заголовков."""
        service_name = self._resolve_service(service_key)
        base_url = self._urls[service_name]
        target_url = f"{base_url}/api/v1/{service_key}"
        if path:
            target_url = f"{target_url}/{path}"

        headers = self._build_headers(request, actor)
        body = await request.body()

        try:
            upstream = await self._client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
            )
        except httpx.ConnectError:
            raise AppError(
                code="service_unavailable",
                message=f"Сервис {service_name} недоступен",
                status_code=502,
            )
        except httpx.TimeoutException:
            raise AppError(
                code="service_timeout",
                message=f"Таймаут при обращении к {service_name}",
                status_code=504,
            )

        response_headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS
        }

        logger.info(
            "%s %s -> %s [%d]",
            request.method,
            request.url.path,
            target_url,
            upstream.status_code,
        )

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()

    def _resolve_service(self, service_key: str) -> str:
        """Определить имя сервиса по ключу из URL."""
        service = self.SERVICE_MAP.get(service_key)
        if not service:
            raise AppError(
                code="unknown_service",
                message=f"Неизвестный сервис: {service_key}",
                status_code=404,
            )
        return service

    def _build_headers(self, request: Request, actor: MeData) -> dict[str, str]:
        """Собрать заголовки для downstream-запроса с данными актора."""
        headers: dict[str, str] = {}

        for key, value in request.headers.items():
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host":
                headers[key] = value

        headers["X-Actor-Id"] = actor.actor_id
        headers["X-Actor-Type"] = actor.actor_type
        headers["X-Permissions"] = ",".join(actor.permissions)
        headers["X-Internal-Token"] = self._internal_token

        request_id = request.headers.get("x-request-id", "")
        if request_id:
            headers["X-Request-Id"] = request_id

        return headers
