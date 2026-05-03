import uuid

from common.exceptions import AppError
from common.logger import setup_logger

from vacancy.repository import VacancyRepository
from vacancy.schemas.vacancy import (
    RequirementRequest,
    VacancyCreateRequest,
    VacancyData,
    VacancyUpdateRequest,
)
from vacancy.services.event_publisher import EventPublisher

logger = setup_logger("vacancy.service")

_VALID_STATUSES = {"draft", "open", "closed", "archived"}
_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"open"},
    "open": {"closed"},
    "closed": {"archived"},
    "archived": set(),
}


class VacancyService:
    """Сервис управления жизненным циклом вакансий."""

    def __init__(self, event_publisher: EventPublisher) -> None:
        self._events = event_publisher

    async def create(
        self,
        body: VacancyCreateRequest,
        repo: VacancyRepository,
    ) -> VacancyData:
        """Создать вакансию со статусом draft и её требованиями."""
        vacancy = await repo.create(
            title=body.title,
            description=body.description,
            location=body.location,
            grade=body.grade,
            department=body.department,
            salary_min=body.salary_min,
            salary_max=body.salary_max,
        )
        if body.requirements:
            await repo.add_requirements(
                vacancy.id,
                [r.model_dump() for r in body.requirements],
            )
        await repo.commit()

        vacancy = await repo.get(vacancy.id)
        result = _to_vacancy_data(vacancy)

        self._events.publish(
            routing_key="vacancy.created",
            event_type="vacancy.created",
            payload={
                "vacancy_id": result.id,
                "status": result.status,
                "changed_fields": [],
            },
        )
        logger.info("Вакансия создана: %s", result.id)
        return result

    async def get(
        self,
        vacancy_id: str,
        repo: VacancyRepository,
    ) -> VacancyData:
        """Получить вакансию по ID."""
        vacancy = await repo.get(_parse_uuid(vacancy_id))
        if not vacancy:
            raise AppError(
                code="not_found",
                message="Вакансия не найдена",
                status_code=404,
            )
        return _to_vacancy_data(vacancy)

    async def update(
        self,
        vacancy_id: str,
        body: VacancyUpdateRequest,
        repo: VacancyRepository,
    ) -> VacancyData:
        """Обновить вакансию и опубликовать событие."""
        uid = _parse_uuid(vacancy_id)
        existing = await repo.get(uid)
        if not existing:
            raise AppError(
                code="not_found",
                message="Вакансия не найдена",
                status_code=404,
            )

        changed_fields: list[str] = []

        if body.status and body.status != existing.status:
            _validate_status_transition(existing.status, body.status)
            changed_fields.append("status")

        fields: dict = {}
        for field in (
            "title",
            "description",
            "department",
            "location",
            "grade",
            "salary_min",
            "salary_max",
            "status",
        ):
            value = getattr(body, field, None)
            if value is not None:
                fields[field] = value
                if field not in changed_fields:
                    changed_fields.append(field)

        if fields:
            await repo.update(uid, **fields)

        if body.requirements is not None:
            await repo.replace_requirements(
                uid,
                [r.model_dump() for r in body.requirements],
            )
            changed_fields.append("requirements")

        await repo.commit()
        vacancy = await repo.get(uid)
        result = _to_vacancy_data(vacancy)

        if changed_fields:
            self._events.publish(
                routing_key="vacancy.updated",
                event_type="vacancy.updated",
                payload={
                    "vacancy_id": result.id,
                    "status": result.status,
                    "changed_fields": changed_fields,
                },
            )
        logger.info("Вакансия обновлена: %s, поля: %s", result.id, changed_fields)
        return result

    async def list_vacancies(
        self,
        repo: VacancyRepository,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        department: str | None = None,
        grade: str | None = None,
        location: str | None = None,
    ) -> tuple[list[VacancyData], int]:
        """Получить список вакансий с фильтрами."""
        vacancies, total = await repo.list_vacancies(
            limit=limit,
            offset=offset,
            status=status,
            department=department,
            grade=grade,
            location=location,
        )
        return [_to_vacancy_data(v) for v in vacancies], total

    async def delete(self, vacancy_id: str, repo: VacancyRepository) -> None:
        """Удалить вакансию по ID."""
        deleted = await repo.delete(_parse_uuid(vacancy_id))
        if not deleted:
            raise AppError(
                code="not_found",
                message="Вакансия не найдена",
                status_code=404,
            )
        await repo.commit()
        logger.info("Вакансия удалена: %s", vacancy_id)


def _parse_uuid(value: str) -> uuid.UUID:
    """Преобразовать строку в UUID."""
    try:
        return uuid.UUID(value)
    except ValueError:
        raise AppError(
            code="invalid_id",
            message="Некорректный формат ID",
            status_code=400,
        )

def _validate_status_transition(current: str, target: str) -> None:
    """Проверить допустимость перехода статуса вакансии."""
    if target not in _VALID_STATUSES:
        raise AppError(
            code="invalid_status",
            message=f"Недопустимый статус: {target}",
            status_code=400,
        )
    allowed = _STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise AppError(
            code="invalid_transition",
            message=f"Переход {current} → {target} недопустим",
            status_code=400,
        )

def _to_vacancy_data(vacancy) -> VacancyData:
    """Преобразовать ORM-модель вакансии в Pydantic-схему."""
    from vacancy.schemas.vacancy import RequirementData

    requirements = []
    for req in (vacancy.requirements or []):
        requirements.append(
            RequirementData(
                id=str(req.id),
                skill=req.skill,
                category=req.category,
                priority=req.priority,
                min_experience_years=(
                    float(req.min_experience_years)
                    if req.min_experience_years
                    else None
                ),
            )
        )
    return VacancyData(
        id=str(vacancy.id),
        title=vacancy.title,
        description=vacancy.description,
        department=vacancy.department,
        location=vacancy.location,
        grade=vacancy.grade or [],
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        status=vacancy.status,
        requirements=requirements,
        created_at=vacancy.created_at.isoformat(),
        updated_at=vacancy.updated_at.isoformat(),
    )
