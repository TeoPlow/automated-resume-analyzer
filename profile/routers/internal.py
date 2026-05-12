import uuid

from fastapi import APIRouter, Depends, Request

from common.auth import require_internal
from common.exceptions import AppError
from common.schemas.base import BaseResponse

from profile.config import ProfileConfig
from profile.repository import ProfileRepository
from profile.schemas.candidate import CandidateBulkRequest, CandidateData

from common.database import Database


def create_router(config: ProfileConfig, db: Database) -> APIRouter:
    """Создать роутер для внутреннего API"""
    router = APIRouter(prefix="/internal/v1", tags=["internal"])

    @router.get("/candidates/active")
    async def get_active_candidates(
        request: Request,
    ) -> BaseResponse[list[CandidateData]]:
        """Получить всех кандидатов с готовым агрегированным профилем"""
        require_internal(request, config.INTERNAL_TOKEN)

        async with db.session() as session:
            repo = ProfileRepository(session)
            candidates = await repo.get_active_candidates()

        return BaseResponse(data=[_to_candidate_data(c) for c in candidates])

    @router.get("/candidates/{candidate_id:uuid}")
    async def get_candidate_internal(
        candidate_id: uuid.UUID,
        request: Request,
    ) -> BaseResponse[CandidateData]:
        """Получить кандидата по ID (внутренний вызов)"""
        require_internal(request, config.INTERNAL_TOKEN)

        async with db.session() as session:
            repo = ProfileRepository(session)
            candidate = await repo.get_candidate(candidate_id)

        if not candidate:
            raise AppError(
                code="not_found",
                message="Кандидат не найден",
                status_code=404,
            )

        return BaseResponse(data=_to_candidate_data(candidate))

    @router.post("/candidates/bulk-get")
    async def bulk_get_candidates(
        body: CandidateBulkRequest,
        request: Request,
    ) -> BaseResponse[list[CandidateData]]:
        """Получить список кандидатов по массиву ID (внутренний вызов)"""
        require_internal(request, config.INTERNAL_TOKEN)

        import uuid as uuid_mod

        uuids = [uuid_mod.UUID(cid) for cid in body.candidate_ids]

        async with db.session() as session:
            repo = ProfileRepository(session)
            candidates = await repo.get_candidates_bulk(uuids)

        return BaseResponse(data=[_to_candidate_data(c) for c in candidates])

    return router


def _to_candidate_data(candidate) -> CandidateData:
    """Преобразовать ORM-модель кандидата в Pydantic-схему"""
    from profile.schemas.candidate import CandidateProfileData

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
