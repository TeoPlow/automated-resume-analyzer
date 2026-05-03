from fastapi import APIRouter, Depends, Query

from common.auth import (
    Actor,
    extract_actor,
    require_admin,
    require_permission,
)
from common.schemas.base import BaseResponse, PaginationData

from common.database import Database
from vacancy.repository import VacancyRepository
from vacancy.schemas.vacancy import (
    VacancyCreateRequest,
    VacancyData,
    VacancyUpdateRequest,
)
from vacancy.services.vacancy_service import VacancyService


def create_router(db: Database, service: VacancyService) -> APIRouter:
    """Создать роутер для работы с вакансиями."""
    router = APIRouter(prefix="/vacancies", tags=["vacancies"])

    @router.post("")
    async def create_vacancy(
        body: VacancyCreateRequest,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[VacancyData]:
        """Создать новую вакансию (статус draft)."""
        require_permission(actor, "vacancies:write")

        async with db.session() as session:
            repo = VacancyRepository(session)
            result = await service.create(body, repo)

        return BaseResponse(data=result)

    @router.get("/{vacancy_id}")
    async def get_vacancy(
        vacancy_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[VacancyData]:
        """Получить вакансию по ID с требованиями."""
        require_permission(actor, "vacancies:read")

        async with db.session() as session:
            repo = VacancyRepository(session)
            result = await service.get(vacancy_id, repo)

        return BaseResponse(data=result)

    @router.patch("/{vacancy_id}")
    async def update_vacancy(
        vacancy_id: str,
        body: VacancyUpdateRequest,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[VacancyData]:
        """Обновить вакансию (поля, статус, требования)."""
        require_permission(actor, "vacancies:write")

        async with db.session() as session:
            repo = VacancyRepository(session)
            result = await service.update(vacancy_id, body, repo)

        return BaseResponse(data=result)

    @router.get("")
    async def list_vacancies(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        status: str | None = None,
        department: str | None = None,
        grade: str | None = None,
        location: str | None = None,
        actor: Actor = Depends(extract_actor),
    ) -> BaseResponse[list[VacancyData]]:
        """Получить список вакансий с фильтрами и пагинацией."""
        require_permission(actor, "vacancies:read")

        async with db.session() as session:
            repo = VacancyRepository(session)
            items, total = await service.list_vacancies(
                repo,
                limit=limit,
                offset=offset,
                status=status,
                department=department,
                grade=grade,
                location=location,
            )

        return BaseResponse(
            data=items,
            pagination=PaginationData(
                limit=limit, offset=offset, total=total
            ),
        )

    @router.delete("/{vacancy_id}", status_code=204)
    async def delete_vacancy(
        vacancy_id: str,
        actor: Actor = Depends(extract_actor),
    ) -> None:
        """Удалить вакансию (только администратор)."""
        require_permission(actor, "vacancies:write")
        require_admin(actor)

        async with db.session() as session:
            repo = VacancyRepository(session)
            await service.delete(vacancy_id, repo)

    return router
