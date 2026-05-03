from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.database import Database
from common.error_handler import register_error_handlers
from common.health import make_health_router
from common.logger import setup_logger
from common.request_id import RequestIdMiddleware

from search.config import SearchConfig
from search.routers import search
from search.services.search_service import SearchService

logger = setup_logger("search")

config = SearchConfig()

db = Database(url=config.DATABASE_URL, echo=config.DB_ECHO)

search_service = SearchService()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Жизненный цикл: подключение к БД (read-only)."""
    logger.info("Search-сервис запущен на порту 8004")
    yield
    await db.dispose()
    logger.info("Search-сервис остановлен")


app = FastAPI(
    title="Search — Resume Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(make_health_router("search"))
app.include_router(search.create_router(config=config, db=db, service=search_service))
