from fastapi import APIRouter, Depends, Query

from common.auth import Actor, extract_actor, require_permission
from common.database import Database
from common.schemas.base import BaseResponse, PaginationData

from search.config import SearchConfig
from search.repository import SearchRepository
from search.schemas.search import (
    CandidateSearchData,
    MatchSearchData,
    SummaryData,
    VacancySearchData,
)
from search.services.search_service import SearchService


def create_router(
    config: SearchConfig,
    db: Database,
    service: SearchService,
) -> APIRouter:
    """Создать роутер поиска."""
    router = APIRouter(prefix="/api/v1/search", tags=["search"])

    @router.get(
        "/candidates",
        response_model=BaseResponse[list[CandidateSearchData]],
    )
    async def search_candidates(
        q: str | None = Query(None, description="Полнотекстовый поиск"),
        skills: str | None = Query(None, description="Навыки через запятую"),
        grade: str | None = None,
        location: str | None = None,
        experience_years_min: float | None = None,
        experience_years_max: float | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        limit: int = Query(default=config.DEFAULT_LIMIT, ge=1, le=config.MAX_LIMIT),
        offset: int = Query(default=0, ge=0),
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[CandidateSearchData]]:
        """Поиск кандидатов с фильтрами и пагинацией."""
        require_permission(actor, "search:use")
        skill_list = _parse_csv(skills) if skills else None
        async with db.session() as session:
            repo = SearchRepository(session)
            data, total = await service.search_candidates(
                repo,
                q=q,
                skills=skill_list,
                grade=grade,
                location=location,
                experience_min=experience_years_min,
                experience_max=experience_years_max,
                salary_min=salary_min,
                salary_max=salary_max,
                limit=limit,
                offset=offset,
            )
        return BaseResponse(
            data=data,
            pagination=PaginationData(limit=limit, offset=offset, total=total),
        )

    @router.get(
        "/vacancies",
        response_model=BaseResponse[list[VacancySearchData]],
    )
    async def search_vacancies(
        status: str | None = None,
        department: str | None = None,
        grade: str | None = None,
        location: str | None = None,
        limit: int = Query(default=config.DEFAULT_LIMIT, ge=1, le=config.MAX_LIMIT),
        offset: int = Query(default=0, ge=0),
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[VacancySearchData]]:
        """Поиск вакансий с фильтрами и пагинацией."""
        require_permission(actor, "search:use")
        async with db.session() as session:
            repo = SearchRepository(session)
            data, total = await service.search_vacancies(
                repo,
                status=status,
                department=department,
                grade=grade,
                location=location,
                limit=limit,
                offset=offset,
            )
        return BaseResponse(
            data=data,
            pagination=PaginationData(limit=limit, offset=offset, total=total),
        )

    @router.get(
        "/matches",
        response_model=BaseResponse[list[MatchSearchData]],
    )
    async def search_matches(
        vacancy_id: str | None = None,
        min_score: float | None = None,
        grade: str | None = None,
        limit: int = Query(default=config.DEFAULT_LIMIT, ge=1, le=config.MAX_LIMIT),
        offset: int = Query(default=0, ge=0),
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[MatchSearchData]]:
        """Поиск результатов матчинга с объединёнными данными."""
        require_permission(actor, "search:use")
        async with db.session() as session:
            repo = SearchRepository(session)
            data, total = await service.search_matches(
                repo,
                vacancy_id=vacancy_id,
                min_score=min_score,
                grade=grade,
                limit=limit,
                offset=offset,
            )
        return BaseResponse(
            data=data,
            pagination=PaginationData(limit=limit, offset=offset, total=total),
        )

    @router.get(
        "/summary",
        response_model=BaseResponse[SummaryData],
    )
    async def get_summary(
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[SummaryData]:
        """Получить агрегированную статистику по системе."""
        require_permission(actor, "search:use")
        async with db.session() as session:
            repo = SearchRepository(session)
            data = await service.get_summary(repo)
        return BaseResponse(data=data)

    return router


def _parse_csv(value: str) -> list[str]:
    """Разобрать строку навыков, разделённых запятой."""
    return [s.strip() for s in value.split(",") if s.strip()]
