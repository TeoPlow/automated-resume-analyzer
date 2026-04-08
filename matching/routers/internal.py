from fastapi import APIRouter, Request

from common.auth import require_internal
from common.database import Database
from common.schemas.base import BaseResponse

from matching.repository import MatchingRepository
from matching.schemas.match import MatchResultData, MatchRunData, MatchRunRequest
from matching.services.matching_service import MatchingService


def create_router(
    db: Database,
    service: MatchingService,
    internal_token: str,
) -> APIRouter:
    """Создать внутренний роутер матчинга."""
    router = APIRouter(prefix="/internal/v1", tags=["internal"])

    @router.post(
        "/run-for-vacancy/{vacancy_id}",
        response_model=BaseResponse[MatchRunData],
    )
    async def run_for_vacancy(
        vacancy_id: str,
        request: Request,
    ) -> BaseResponse[MatchRunData]:
        """Запустить матчинг для вакансии (вызывается event consumer)."""
        require_internal(request, internal_token)
        body = MatchRunRequest(vacancy_id=vacancy_id)
        async with db.session() as session:
            repo = MatchingRepository(session)
            data = await service.run(body, repo)
        return BaseResponse(data=data)

    @router.get(
        "/results/by-vacancy/{vacancy_id}",
        response_model=BaseResponse[list[MatchResultData]],
    )
    async def get_results_by_vacancy(
        vacancy_id: str,
        request: Request,
    ) -> BaseResponse[list[MatchResultData]]:
        """Получить результаты матчинга для вакансии."""
        require_internal(request, internal_token)
        async with db.session() as session:
            repo = MatchingRepository(session)
            data = await service.get_vacancy_results(vacancy_id, repo)
        return BaseResponse(data=data)

    return router
