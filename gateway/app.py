from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.error_handler import register_error_handlers
from common.health import make_health_router
from common.logger import setup_logger
from common.request_id import RequestIdMiddleware

from gateway.config import GatewayConfig
from gateway.routers import auth, integrations, proxy
from gateway.services.auth_service import AuthService, InMemoryAuthStore
from gateway.services.jwt_service import JwtService
from gateway.services.proxy_service import ProxyService
from gateway.services.rate_limiter import SlidingWindowRateLimiter

logger = setup_logger("gateway")

config = GatewayConfig()

jwt_service = JwtService(
    secret=config.JWT_SECRET,
    access_ttl=config.JWT_ACCESS_TTL,
    refresh_ttl=config.JWT_REFRESH_TTL,
)
auth_store = InMemoryAuthStore()
auth_service = AuthService(config=config, store=auth_store, jwt=jwt_service)

rate_limiter = SlidingWindowRateLimiter(
    max_requests=config.RATE_LIMIT_MAX,
    window_seconds=config.RATE_LIMIT_WINDOW,
)
proxy_service = ProxyService(config=config)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Жизненный цикл приложения: инициализация и завершение ресурсов."""
    logger.info("Gateway запущен на порту 8000")
    yield
    await proxy_service.close()
    logger.info("Gateway остановлен")


app = FastAPI(
    title="Gateway — Resume Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(make_health_router("gateway"))
app.include_router(
    auth.create_router(auth_service),
    prefix="/api/v1",
)
app.include_router(
    integrations.create_router(auth_service),
    prefix="/api/v1",
)
app.include_router(
    proxy.create_router(auth_service, proxy_service, rate_limiter),
    prefix="/api/v1",
)
