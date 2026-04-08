import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vacancy.models.vacancy import Vacancy, VacancyRequirement


class VacancyRepository:
    """Доступ к данным вакансий и их требований."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        title: str,
        description: str,
        location: str,
        grade: list[str],
        department: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
    ) -> Vacancy:
        """Создать вакансию со статусом draft."""
        vacancy = Vacancy(
            title=title,
            description=description,
            location=location,
            grade=grade,
            department=department,
            salary_min=salary_min,
            salary_max=salary_max,
            status="draft",
        )
        self._session.add(vacancy)
        await self._session.flush()
        return vacancy

    async def add_requirements(
        self,
        vacancy_id: uuid.UUID,
        requirements: list[dict],
    ) -> list[VacancyRequirement]:
        """Добавить требования к вакансии."""
        entities = []
        for req in requirements:
            entity = VacancyRequirement(
                vacancy_id=vacancy_id,
                skill=req["skill"].lower().strip(),
                category=req["category"],
                priority=req["priority"],
                min_experience_years=req.get("min_experience_years"),
            )
            self._session.add(entity)
            entities.append(entity)
        await self._session.flush()
        return entities

    async def replace_requirements(
        self,
        vacancy_id: uuid.UUID,
        requirements: list[dict],
    ) -> list[VacancyRequirement]:
        """Заменить все требования вакансии новым набором."""
        stmt = select(VacancyRequirement).where(
            VacancyRequirement.vacancy_id == vacancy_id
        )
        result = await self._session.execute(stmt)
        for old in result.scalars().all():
            await self._session.delete(old)
        await self._session.flush()
        return await self.add_requirements(vacancy_id, requirements)

    async def get(self, vacancy_id: uuid.UUID) -> Vacancy | None:
        """Получить вакансию по ID с требованиями."""
        return await self._session.get(Vacancy, vacancy_id)

    async def update(
        self, vacancy_id: uuid.UUID, **fields
    ) -> Vacancy | None:
        """Обновить поля вакансии."""
        values = {k: v for k, v in fields.items() if v is not None}
        if not values:
            return await self.get(vacancy_id)
        values["updated_at"] = datetime.now(timezone.utc)
        stmt = (
            update(Vacancy).where(Vacancy.id == vacancy_id).values(**values)
        )
        await self._session.execute(stmt)
        return await self.get(vacancy_id)

    async def list_vacancies(
        self,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        department: str | None = None,
        grade: str | None = None,
        location: str | None = None,
    ) -> tuple[list[Vacancy], int]:
        """Получить список вакансий с фильтрами и пагинацией."""
        stmt = select(Vacancy)
        count_stmt = select(func.count(Vacancy.id))

        if status:
            stmt = stmt.where(Vacancy.status == status)
            count_stmt = count_stmt.where(Vacancy.status == status)
        if department:
            stmt = stmt.where(Vacancy.department == department)
            count_stmt = count_stmt.where(Vacancy.department == department)
        if grade:
            stmt = stmt.where(Vacancy.grade.any(grade))  # type: ignore[arg-type]
            count_stmt = count_stmt.where(Vacancy.grade.any(grade))  # type: ignore[arg-type]
        if location:
            stmt = stmt.where(Vacancy.location.ilike(f"%{location}%"))
            count_stmt = count_stmt.where(
                Vacancy.location.ilike(f"%{location}%")
            )

        stmt = stmt.order_by(Vacancy.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self._session.execute(stmt)
        vacancies = list(result.scalars().all())

        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar() or 0

        return vacancies, total

    async def get_bulk(
        self, vacancy_ids: list[uuid.UUID]
    ) -> list[Vacancy]:
        """Получить список вакансий по массиву ID."""
        stmt = select(Vacancy).where(Vacancy.id.in_(vacancy_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""
        await self._session.commit()
