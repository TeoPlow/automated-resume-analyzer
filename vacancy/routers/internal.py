import uuid as uuid_mod

from fastapi import APIRouter, Request

from common.auth import require_internal
from common.exceptions import AppError
from common.schemas.base import BaseResponse

from common.database import Database
from vacancy.config import VacancyConfig
from vacancy.repository import VacancyRepository
from vacancy.schemas.vacancy import VacancyBulkRequest, VacancyData
from vacancy.services.vacancy_service import _to_vacancy_data


def create_router(config: VacancyConfig, db: Database) -> APIRouter:
    """Создать роутер для внутреннего API (защищён X-Internal-Token)."""
    router = APIRouter(prefix="/internal/v1", tags=["internal"])

    @router.get("/vacancies/{vacancy_id}")
    async def get_vacancy_internal(
        vacancy_id: str,
        request: Request,
    ) -> BaseResponse[VacancyData]:
        """Получить вакансию по ID (внутренний вызов)."""
        require_internal(request, config.INTERNAL_TOKEN)

        uid = _parse_uuid(vacancy_id)
        async with db.session() as session:
            repo = VacancyRepository(session)
            vacancy = await repo.get(uid)

        if not vacancy:
            raise AppError(
                code="not_found",
                message="Вакансия не найдена",
                status_code=404,
            )

        return BaseResponse(data=_to_vacancy_data(vacancy))

    @router.post("/vacancies/bulk-get")
    async def bulk_get_vacancies(
        body: VacancyBulkRequest,
        request: Request,
    ) -> BaseResponse[list[VacancyData]]:
        """Получить список вакансий по массиву ID (внутренний вызов)."""
        require_internal(request, config.INTERNAL_TOKEN)

        uuids = [uuid_mod.UUID(vid) for vid in body.vacancy_ids]
        async with db.session() as session:
            repo = VacancyRepository(session)
            vacancies = await repo.get_bulk(uuids)

        return BaseResponse(data=[_to_vacancy_data(v) for v in vacancies])

    return router


def _parse_uuid(value: str) -> uuid_mod.UUID:
    """Преобразовать строку в UUID."""
    try:
        return uuid_mod.UUID(value)
    except ValueError:
        raise AppError(
            code="invalid_id",
            message="Некорректный формат ID",
            status_code=400,
        )
