from fastapi import APIRouter, Depends

from common.auth import (
    Actor,
    extract_actor,
    require_admin,
    require_permission,
)
from common.exceptions import AppError
from common.schemas.base import BaseResponse

from profile.repository import ProfileRepository
from profile.schemas.candidate import (
    CandidateData,
    CandidateProfileData,
    CandidateUpdateRequest,
)
from profile.schemas.resume import ResumeData

from common.database import Database


def create_router(db: Database) -> APIRouter:
    """Создать роутер для работы с кандидатами."""
    router = APIRouter(prefix="/candidates", tags=["candidates"])

    @router.get("/{candidate_id}")
    async def get_candidate(
        candidate_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[CandidateData]:
        """Получить полный профиль кандидата по ID."""
        require_permission(actor, "candidates:read")

        async with db.session() as session:
            repo = ProfileRepository(session)
            candidate = await repo.get_candidate(
                _parse_uuid(candidate_id)
            )

        if not candidate:
            raise AppError(
                code="not_found",
                message="Кандидат не найден",
                status_code=404,
            )

        return BaseResponse(data=_to_candidate_data(candidate))

    @router.patch("/{candidate_id}")
    async def update_candidate(
        candidate_id: str,
        body: CandidateUpdateRequest,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[CandidateData]:
        """Обновить данные кандидата (ФИО, email, телефон)."""
        require_permission(actor, "candidates:write")

        async with db.session() as session:
            repo = ProfileRepository(session)
            candidate = await repo.update_candidate(
                _parse_uuid(candidate_id),
                full_name=body.full_name,
                email=body.email,
                phone=body.phone,
            )
            await repo.commit()

        if not candidate:
            raise AppError(
                code="not_found",
                message="Кандидат не найден",
                status_code=404,
            )

        return BaseResponse(data=_to_candidate_data(candidate))

    @router.get("/{candidate_id}/resumes")
    async def get_candidate_resumes(
        candidate_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[ResumeData]]:
        """Получить все резюме кандидата."""
        require_permission(actor, "candidates:read")

        async with db.session() as session:
            repo = ProfileRepository(session)
            resumes = await repo.get_candidate_resumes(
                _parse_uuid(candidate_id)
            )

        return BaseResponse(
            data=[_to_resume_data(r) for r in resumes]
        )

    @router.delete("/{candidate_id}", status_code=204)
    async def delete_candidate(
        candidate_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> None:
        """Удалить кандидата (только администратор)."""
        require_permission(actor, "candidates:write")
        require_admin(actor)

        async with db.session() as session:
            repo = ProfileRepository(session)
            deleted = await repo.delete_candidate(_parse_uuid(candidate_id))
            if not deleted:
                raise AppError(
                    code="not_found",
                    message="Кандидат не найден",
                    status_code=404,
                )
            await repo.commit()

    return router


# --- Приватные функции ---


def _parse_uuid(value: str):
    """Преобразовать строку в UUID."""
    import uuid

    try:
        return uuid.UUID(value)
    except ValueError:
        raise AppError(
            code="invalid_id",
            message="Некорректный формат ID",
            status_code=400,
        )


def _to_candidate_data(candidate) -> CandidateData:
    """Преобразовать ORM-модель кандидата в Pydantic-схему."""
    profile = None
    if candidate.profile:
        p = candidate.profile
        profile = CandidateProfileData(
            skills=p.skills or [],
            grade=p.grade,
            location=p.location,
            experience_years=float(p.experience_years) if p.experience_years else None,
            salary_expectation=p.salary_expectation,
            data=p.data or {},
        )
    return CandidateData(
        id=str(candidate.id),
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        created_at=candidate.created_at.isoformat(),
        updated_at=candidate.updated_at.isoformat(),
        profile=profile,
    )


def _to_resume_data(resume) -> ResumeData:
    """Преобразовать ORM-модель резюме в Pydantic-схему."""
    from profile.schemas.resume import ParsedData

    parsed = None
    if resume.parsed_data:
        parsed = ParsedData.model_validate(resume.parsed_data)
    return ResumeData(
        id=str(resume.id),
        file_key=resume.file_key,
        source=resume.source,
        external_id=resume.external_id,
        status=resume.status,
        parsed_data=parsed,
        error_detail=resume.error_detail,
        created_at=resume.created_at.isoformat(),
    )
