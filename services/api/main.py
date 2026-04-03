import hashlib
import importlib
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from http import HTTPStatus
from typing import Annotated, Any
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from libs import (
    IntegrationKeyCreateRequest,
    IntegrationKeyCreateResponse,
    IntegrationKeyInfo,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
    install_exception_handlers,
    install_health_endpoint,
    raise_http,
)
from auth import (
    Actor,
    authenticate,
    create_integration_api_key,
    list_integration_api_keys,
    login_user,
    refresh_user_tokens,
    logout_user,
    require_admin,
    revoke_integration_api_key,
    rotate_integration_api_key,
)


PROXY_TIMEOUT_SECONDS = float(os.getenv("GATEWAY_PROXY_TIMEOUT_SECONDS", "15"))
INTERNAL_TOKEN = os.getenv("GATEWAY_INTERNAL_TOKEN")

RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

SERVICE_BASE_URLS: dict[str, str] = {
    "profiles": os.getenv("PROFILE_SERVICE_URL", "http://profile:8000"),
    "vacancies": os.getenv("VACANCY_SERVICE_URL", "http://vacancy:8000"),
    "matching": os.getenv("MATCHING_SERVICE_URL", "http://matching:8000"),
    "search": os.getenv("SEARCH_SERVICE_URL", "http://search:8000"),
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

httpx_module: Any | None = None


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        if self.max_requests <= 0:
            return True

        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < window_start:
                events.popleft()

            if len(events) >= self.max_requests:
                return False

            events.append(now)
            return True


rate_limiter = SlidingWindowRateLimiter(
    max_requests=RATE_LIMIT_MAX_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)


def _build_roles(actor: Actor) -> str:
    if actor.actor_type == "integration":
        return "integration"
    return "admin,hr" if actor.is_admin else "hr"


def _load_httpx() -> Any:
    global httpx_module
    if httpx_module is None:
        try:
            httpx_module = importlib.import_module("httpx")
        except ModuleNotFoundError as exc:
            raise_http(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "missing_dependency",
                "Gateway proxy dependency httpx is not installed",
                details={"dependency": str(exc.name)},
            )
    return httpx_module


def _extract_rate_limit_key(request: Request) -> str:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        digest = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()[:16]
        return f"api_key:{digest}"

    authorization = request.headers.get("authorization")
    if authorization:
        digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:16]
        return f"auth:{digest}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _filtered_forward_headers(request: Request, actor: Actor) -> dict[str, str]:
    outbound_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() not in {"x-request-id", "x-actor-id", "x-actor-type", "x-roles", "x-is-admin", "x-internal-token"}
    }

    outbound_headers["X-Request-Id"] = request.state.request_id
    outbound_headers["X-Actor-Id"] = actor.actor_id
    outbound_headers["X-Actor-Type"] = actor.actor_type
    outbound_headers["X-Roles"] = _build_roles(actor)
    outbound_headers["X-Is-Admin"] = "true" if actor.is_admin else "false"

    if INTERNAL_TOKEN:
        outbound_headers["X-Internal-Token"] = INTERNAL_TOKEN

    return outbound_headers


def _build_upstream_path(service: str, path: str, method: str) -> str:
    cleaned_path = path.strip("/")
    if service == "profiles" and method.upper() == "POST" and cleaned_path == "resumes/upload":
        # Backward compatibility while profile service still has legacy upload endpoint.
        return "/resumes"

    if cleaned_path:
        return f"/api/v1/{service}/{cleaned_path}"
    return f"/api/v1/{service}"


async def _proxy_service_request(request: Request, service: str, path: str, actor: Actor) -> Response:
    if service not in SERVICE_BASE_URLS:
        raise_http(HTTPStatus.NOT_FOUND, "route_not_found", "Unknown service route")

    upstream_base = SERVICE_BASE_URLS[service].rstrip("/")
    upstream_path = _build_upstream_path(service=service, path=path, method=request.method)
    upstream_url = f"{upstream_base}{upstream_path}"

    outbound_headers = _filtered_forward_headers(request=request, actor=actor)
    body = await request.body()
    httpx = _load_httpx()

    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            upstream_response = await client.request(
                method=request.method,
                url=upstream_url,
                params=request.query_params.multi_items(),
                content=body,
                headers=outbound_headers,
            )
    except httpx.TimeoutException as exc:
        raise_http(
            HTTPStatus.GATEWAY_TIMEOUT,
            "upstream_timeout",
            "Upstream service timed out",
            details={"service": service},
        )
    except httpx.RequestError as exc:
        raise_http(
            HTTPStatus.BAD_GATEWAY,
            "upstream_unreachable",
            "Cannot reach upstream service",
            details={"service": service, "reason": str(exc)},
        )

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    response_headers["X-Request-Id"] = request.state.request_id

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )


app = FastAPI(title="API-Gateway")
install_exception_handlers(app)
install_health_endpoint(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id

    if not request.url.path.startswith("/api/v1") or request.url.path == "/api/v1/health":
        return await call_next(request)

    key = _extract_rate_limit_key(request)
    if not rate_limiter.is_allowed(key):
        return JSONResponse(
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            content={
                "status": "error",
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests",
                    "details": {
                        "limit": RATE_LIMIT_MAX_REQUESTS,
                        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
                        "request_id": request_id,
                    },
                },
            },
            headers={"X-Request-Id": request_id},
        )

    return await call_next(request)


@app.get("/api/v1/health")
def api_v1_health() -> dict[str, Any]:
    return {"status": "ok", "service": app.title}


@app.post("/api/v1/auth/login", response_model=TokenPair)
def login(payload: LoginRequest) -> TokenPair:
    return login_user(payload.username, payload.password)


@app.post("/api/v1/auth/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest) -> TokenPair:
    return refresh_user_tokens(payload.refresh_token)


@app.post("/api/v1/auth/logout", status_code=HTTPStatus.NO_CONTENT)
def logout(payload: LogoutRequest) -> None:
    logout_user(payload.refresh_token)


@app.get("/api/v1/me", response_model=MeResponse)
def me(actor: Annotated[Actor, Depends(authenticate)]) -> MeResponse:
    return MeResponse(actor_id=actor.actor_id, actor_type=actor.actor_type, is_admin=actor.is_admin)


@app.post("/api/v1/integrations/keys", response_model=IntegrationKeyCreateResponse, status_code=HTTPStatus.CREATED)
def create_integration_key(
    payload: IntegrationKeyCreateRequest,
    _: Annotated[Actor, Depends(require_admin)],
) -> IntegrationKeyCreateResponse:
    return create_integration_api_key(payload.name)


@app.get("/api/v1/integrations/keys", response_model=list[IntegrationKeyInfo])
def list_integration_keys(_: Annotated[Actor, Depends(require_admin)]) -> list[IntegrationKeyInfo]:
    return list_integration_api_keys()


@app.post("/api/v1/integrations/keys/{key_id}/rotate", response_model=IntegrationKeyCreateResponse)
def rotate_integration_key(
    key_id: str,
    _: Annotated[Actor, Depends(require_admin)],
) -> IntegrationKeyCreateResponse:
    return rotate_integration_api_key(key_id)


@app.delete("/api/v1/integrations/keys/{key_id}", status_code=HTTPStatus.NO_CONTENT)
def revoke_integration_key(key_id: str, _: Annotated[Actor, Depends(require_admin)]) -> None:
    revoke_integration_api_key(key_id)


@app.api_route(
    "/api/v1/{service}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    include_in_schema=False,
)
@app.api_route(
    "/api/v1/{service}/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    include_in_schema=False,
)
async def proxy_domain_routes(
    service: str,
    request: Request,
    actor: Annotated[Actor, Depends(authenticate)],
    path: str = "",
) -> Response:
    return await _proxy_service_request(request=request, service=service, path=path, actor=actor)
