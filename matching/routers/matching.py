from fastapi import APIRouter, Depends

from common.auth import Actor, extract_actor, require_permission
from common.database import Database
from common.schemas.base import BaseResponse

from matching.repository import MatchingRepository
from matching.schemas.match import MatchResultData, MatchRunData, MatchRunRequest
from matching.services.matching_service import MatchingService


def create_router(db: Database, service: MatchingService) -> APIRouter:
    """Создать роутер матчинга"""
    router = APIRouter(prefix="/api/v1/matching", tags=["matching"])

    @router.post("/run", response_model=BaseResponse[MatchRunData])
    async def run_matching(
        body: MatchRunRequest,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[MatchRunData]:
        """Запустить матчинг кандидатов по вакансии"""
        require_permission(actor, "matching:run")
        async with db.session() as session:
            repo = MatchingRepository(session)
            data = await service.run(body, repo)
        return BaseResponse(data=data)

    @router.get(
        "/results/{run_id}",
        response_model=BaseResponse[list[MatchResultData]],
    )
    async def get_results(
        run_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[MatchResultData]]:
        """Получить результаты матчинга по ID запуска"""
        require_permission(actor, "matching:read")
        async with db.session() as session:
            repo = MatchingRepository(session)
            data = await service.get_results(run_id, repo)
        return BaseResponse(data=data)

    @router.get(
        "/vacancies/{vacancy_id}",
        response_model=BaseResponse[list[MatchResultData]],
    )
    async def get_vacancy_results(
        vacancy_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[MatchResultData]]:
        """Получить лучших кандидатов для вакансии"""
        require_permission(actor, "matching:read")
        async with db.session() as session:
            repo = MatchingRepository(session)
            data = await service.get_vacancy_results(vacancy_id, repo)
        return BaseResponse(data=data)

    @router.get(
        "/candidates/{candidate_id}/vacancies",
        response_model=BaseResponse[list[MatchResultData]],
    )
    async def get_candidate_vacancies(
        candidate_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[MatchResultData]]:
        """Получить подходящие вакансии для кандидата"""
        require_permission(actor, "matching:read")
        async with db.session() as session:
            repo = MatchingRepository(session)
            data = await service.get_candidate_vacancies(candidate_id, repo)
        return BaseResponse(data=data)

    return router
