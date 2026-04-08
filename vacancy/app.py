from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.database import Database
from common.error_handler import register_error_handlers
from common.health import make_health_router
from common.logger import setup_logger
from common.request_id import RequestIdMiddleware

from vacancy.config import VacancyConfig
from vacancy.routers import internal, vacancies
from vacancy.services.event_publisher import EventPublisher
from vacancy.services.vacancy_service import VacancyService

logger = setup_logger("vacancy")

config = VacancyConfig()

db = Database(url=config.DATABASE_URL, echo=config.DB_ECHO)

event_publisher = EventPublisher(
    rabbitmq_url=config.RABBITMQ_URL,
    exchange=config.EXCHANGE_NAME,
    dlx=config.DLX_NAME,
)

vacancy_service = VacancyService(event_publisher=event_publisher)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Жизненный цикл: создание таблиц, подключение к RabbitMQ."""
    await db.create_tables()
    event_publisher.connect()
    logger.info("Vacancy-сервис запущен на порту 8002")
    yield
    event_publisher.close()
    await db.dispose()
    logger.info("Vacancy-сервис остановлен")


app = FastAPI(
    title="Vacancy — Resume Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(make_health_router("vacancy"))
app.include_router(
    vacancies.create_router(db, vacancy_service),
    prefix="/api/v1",
)
app.include_router(
    internal.create_router(config, db),
)
