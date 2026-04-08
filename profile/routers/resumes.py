import asyncio

from fastapi import APIRouter, Depends, Request, UploadFile

from common.auth import Actor, extract_actor, require_permission
from common.schemas.base import BaseResponse

from profile.config import ProfileConfig
from profile.repository import ProfileRepository
from profile.schemas.resume import ResumeUploadData
from profile.services.event_publisher import EventPublisher
from profile.services.file_validator import FileValidator
from profile.services.resume_processor import ResumeProcessor
from profile.services.storage import FileStorage

from common.database import Database


def create_router(
    config: ProfileConfig,
    db: Database,
    file_validator: FileValidator,
    file_storage: FileStorage,
    event_publisher: EventPublisher,
    resume_processor: ResumeProcessor,
) -> APIRouter:
    """Создать роутер для загрузки резюме."""
    router = APIRouter(prefix="/resumes", tags=["resumes"])

    @router.post("/upload")
    async def upload_resume(
        file: UploadFile,
        source: str,
        external_id: str | None = None,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[ResumeUploadData]:
        """Загрузить резюме: валидация → MinIO → БД → событие.

        Возвращает resume_id и статус uploaded.
        Обработка (парсинг) выполняется асинхронно.
        """
        require_permission(actor, "resumes:upload")

        content = await file.read()
        extension = file_validator.validate(file.filename or "", content)

        file_key = file_storage.upload(content, extension)

        async with db.session() as session:
            repo = ProfileRepository(session)
            resume = await repo.create_resume(
                file_key=file_key,
                source=source,
                external_id=external_id,
            )
            await repo.commit()
            resume_id = resume.id

        event_publisher.publish(
            routing_key="resume.uploaded",
            event_type="resume.uploaded",
            payload={
                "resume_id": str(resume_id),
                "candidate_id": None,
                "file_key": file_key,
                "source": source,
            },
        )

        asyncio.create_task(
            _process_in_background(resume_id, file_key, db, resume_processor)
        )

        return BaseResponse(
            data=ResumeUploadData(
                resume_id=str(resume_id),
                status="uploaded",
            )
        )

    return router


# --- Приватные функции ---


async def _process_in_background(
    resume_id, file_key: str, db: Database, processor: ResumeProcessor
) -> None:
    """Запустить обработку резюме в фоне."""
    async with db.session() as session:
        repo = ProfileRepository(session)
        await processor.process(resume_id, file_key, repo)
