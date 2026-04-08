from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.database import Database
from common.error_handler import register_error_handlers
from common.health import make_health_router
from common.logger import setup_logger
from common.request_id import RequestIdMiddleware

from profile.config import ProfileConfig
from profile.routers import candidates, internal, resumes
from profile.services.event_publisher import EventPublisher
from profile.services.file_validator import FileValidator
from profile.services.llm_parser import LlmParser
from profile.services.resume_processor import ResumeProcessor
from profile.services.storage import FileStorage
from profile.services.text_extractor import TextExtractor

logger = setup_logger("profile")

config = ProfileConfig()

db = Database(url=config.DATABASE_URL, echo=config.DB_ECHO)

file_validator = FileValidator(
    max_size=config.MAX_FILE_SIZE,
    allowed_extensions=config.ALLOWED_EXTENSIONS,
)

file_storage = FileStorage(
    endpoint=config.MINIO_ENDPOINT,
    access_key=config.MINIO_ACCESS_KEY,
    secret_key=config.MINIO_SECRET_KEY,
    bucket=config.MINIO_BUCKET,
    use_ssl=config.MINIO_USE_SSL,
)

text_extractor = TextExtractor()

llm_parser = LlmParser(
    ollama_url=config.OLLAMA_URL,
    model=config.LLM_MODEL,
    max_retries=config.LLM_MAX_RETRIES,
)

event_publisher = EventPublisher(
    rabbitmq_url=config.RABBITMQ_URL,
    exchange=config.EXCHANGE_NAME,
    dlx=config.DLX_NAME,
)

resume_processor = ResumeProcessor(
    storage=file_storage,
    text_extractor=text_extractor,
    llm_parser=llm_parser,
    event_publisher=event_publisher,
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Жизненный цикл: создание таблиц, подключение к RabbitMQ."""
    await db.create_tables()
    event_publisher.connect()
    logger.info("Profile-сервис запущен на порту 8001")
    yield
    event_publisher.close()
    await db.dispose()
    logger.info("Profile-сервис остановлен")


app = FastAPI(
    title="Profile — Resume Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(make_health_router("profile"))
app.include_router(
    resumes.create_router(
        config=config,
        db=db,
        file_validator=file_validator,
        file_storage=file_storage,
        event_publisher=event_publisher,
        resume_processor=resume_processor,
    ),
    prefix="/api/v1/profiles",
)
app.include_router(
    candidates.create_router(db),
    prefix="/api/v1/profiles",
)
app.include_router(
    internal.create_router(config, db),
)
