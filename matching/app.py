from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.database import Database
from common.error_handler import register_error_handlers
from common.health import make_health_router
from common.logger import setup_logger
from common.request_id import RequestIdMiddleware

from matching.config import MatchingConfig
from matching.routers import internal, matching
from matching.services.clients import ServiceClient
from matching.services.event_publisher import EventPublisher
from matching.services.matching_service import MatchingService
from matching.services.scorer import CandidateScorer

logger = setup_logger("matching")

config = MatchingConfig()

db = Database(url=config.DATABASE_URL, echo=config.DB_ECHO)

scorer = CandidateScorer(embedding_model_name=config.EMBEDDING_MODEL)

client = ServiceClient(
    profile_url=config.PROFILE_URL,
    vacancy_url=config.VACANCY_URL,
    internal_token=config.INTERNAL_TOKEN,
)

event_publisher = EventPublisher(
    rabbitmq_url=config.RABBITMQ_URL,
    exchange=config.EXCHANGE_NAME,
    dlx=config.DLX_NAME,
)

matching_service = MatchingService(
    config=config,
    scorer=scorer,
    client=client,
    events=event_publisher,
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Жизненный цикл: создание таблиц, подключение к RabbitMQ"""
    await db.create_tables()
    event_publisher.connect()
    logger.info("Matching-сервис запущен на порту 8003")
    yield
    event_publisher.close()
    await client.close()
    await db.dispose()
    logger.info("Matching-сервис остановлен")


app = FastAPI(
    title="Matching — Resume Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(make_health_router("matching"))
app.include_router(matching.create_router(db=db, service=matching_service))
app.include_router(
    internal.create_router(
        db=db,
        service=matching_service,
        internal_token=config.INTERNAL_TOKEN,
    )
)
