import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from matching.models.match import MatchExplanation, MatchResult, MatchRun
from profile.models.candidate import Candidate, CandidateProfile, Resume
from vacancy.models.vacancy import Vacancy, VacancyRequirement

from common.logger import setup_logger

logger = setup_logger("search.repository")


class SearchRepository:
    """Read-only доступ ко всем таблицам для поиска и агрегации."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_candidates(
        self,
        q: str | None = None,
        skills: list[str] | None = None,
        grade: str | None = None,
        location: str | None = None,
        experience_min: float | None = None,
        experience_max: float | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[Candidate, CandidateProfile | None]], int]:
        """Поиск кандидатов с фильтрами и полнотекстовым поиском."""
        stmt = (
            select(Candidate, CandidateProfile)
            .outerjoin(
                CandidateProfile,
                Candidate.id == CandidateProfile.candidate_id,
            )
        )
        count_stmt = (
            select(func.count(Candidate.id))
            .outerjoin(
                CandidateProfile,
                Candidate.id == CandidateProfile.candidate_id,
            )
        )

        stmt, count_stmt = _apply_candidate_filters(
            stmt, count_stmt, q, skills, grade, location,
            experience_min, experience_max, salary_min, salary_max,
        )

        stmt = stmt.order_by(Candidate.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self._session.execute(stmt)
        rows = [(row[0], row[1]) for row in result.all()]

        total_result = await self._session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        return rows, total

    async def search_vacancies(
        self,
        status: str | None = None,
        department: str | None = None,
        grade: str | None = None,
        location: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Vacancy], int]:
        """Поиск вакансий с фильтрами."""
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

    async def search_matches(
        self,
        vacancy_id: str | None = None,
        min_score: float | None = None,
        grade: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[MatchResult, Candidate, Vacancy]], int]:
        """Поиск результатов матчинга с объединёнными данными."""
        stmt = (
            select(MatchResult, Candidate, Vacancy)
            .join(Candidate, MatchResult.candidate_id == Candidate.id)
            .join(Vacancy, MatchResult.vacancy_id == Vacancy.id)
        )
        count_stmt = (
            select(func.count(MatchResult.id))
            .join(Candidate, MatchResult.candidate_id == Candidate.id)
            .join(Vacancy, MatchResult.vacancy_id == Vacancy.id)
        )

        if vacancy_id:
            uid = uuid.UUID(vacancy_id)
            stmt = stmt.where(MatchResult.vacancy_id == uid)
            count_stmt = count_stmt.where(MatchResult.vacancy_id == uid)
        if min_score is not None:
            stmt = stmt.where(MatchResult.final_score >= min_score)
            count_stmt = count_stmt.where(MatchResult.final_score >= min_score)
        if grade:
            stmt = stmt.join(
                CandidateProfile,
                Candidate.id == CandidateProfile.candidate_id,
            ).where(CandidateProfile.grade == grade)
            count_stmt = count_stmt.join(
                CandidateProfile,
                Candidate.id == CandidateProfile.candidate_id,
            ).where(CandidateProfile.grade == grade)

        stmt = stmt.order_by(MatchResult.final_score.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self._session.execute(stmt)
        rows = [(row[0], row[1], row[2]) for row in result.all()]

        total_result = await self._session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        return rows, total

    async def get_summary(self) -> dict[str, Any]:
        """Получить агрегированную статистику по всей системе."""
        total_candidates = await self._count(Candidate)
        total_vacancies = await self._count(Vacancy)
        total_matches = await self._count(MatchResult)

        grades = await self._aggregate_grades()
        top_skills = await self._aggregate_skills(limit=20)
        locations = await self._aggregate_locations()

        return {
            "total_candidates": total_candidates,
            "total_vacancies": total_vacancies,
            "total_matches": total_matches,
            "grades": grades,
            "top_skills": top_skills,
            "locations": locations,
        }

    async def _count(self, model) -> int:
        """Подсчитать количество записей в таблице."""
        stmt = select(func.count(model.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def _aggregate_grades(self) -> list[dict]:
        """Агрегация кандидатов по грейдам."""
        stmt = (
            select(
                CandidateProfile.grade,
                func.count(CandidateProfile.id).label("count"),
            )
            .where(CandidateProfile.grade.isnot(None))
            .group_by(CandidateProfile.grade)
            .order_by(func.count(CandidateProfile.id).desc())
        )
        result = await self._session.execute(stmt)
        return [{"grade": row.grade, "count": row.count} for row in result.all()]

    async def _aggregate_skills(self, limit: int = 20) -> list[dict]:
        """Агрегация по навыкам (unnest ARRAY)."""
        stmt = text(
            "SELECT skill, COUNT(*) as cnt "
            "FROM candidate_profiles, unnest(skills) AS skill "
            "GROUP BY skill ORDER BY cnt DESC LIMIT :lim"
        )
        result = await self._session.execute(stmt, {"lim": limit})
        return [{"skill": row.skill, "count": row.cnt} for row in result.all()]

    async def _aggregate_locations(self) -> list[dict]:
        """Агрегация кандидатов по локациям."""
        stmt = (
            select(
                CandidateProfile.location,
                func.count(CandidateProfile.id).label("count"),
            )
            .where(CandidateProfile.location.isnot(None))
            .group_by(CandidateProfile.location)
            .order_by(func.count(CandidateProfile.id).desc())
        )
        result = await self._session.execute(stmt)
        return [
            {"location": row.location, "count": row.count}
            for row in result.all()
        ]


def _apply_candidate_filters(stmt, count_stmt, q, skills, grade, location,
                              experience_min, experience_max,
                              salary_min, salary_max):
    """Применить фильтры к запросу поиска кандидатов."""
    if q:
        pattern = f"%{q}%"
        condition = (
            Candidate.full_name.ilike(pattern)
            | CandidateProfile.skills.any(q)
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    if skills:
        for skill in skills:
            stmt = stmt.where(CandidateProfile.skills.any(skill))
            count_stmt = count_stmt.where(CandidateProfile.skills.any(skill))

    if grade:
        stmt = stmt.where(CandidateProfile.grade == grade)
        count_stmt = count_stmt.where(CandidateProfile.grade == grade)

    if location:
        stmt = stmt.where(CandidateProfile.location.ilike(f"%{location}%"))
        count_stmt = count_stmt.where(
            CandidateProfile.location.ilike(f"%{location}%")
        )

    if experience_min is not None:
        stmt = stmt.where(CandidateProfile.experience_years >= experience_min)
        count_stmt = count_stmt.where(
            CandidateProfile.experience_years >= experience_min
        )

    if experience_max is not None:
        stmt = stmt.where(CandidateProfile.experience_years <= experience_max)
        count_stmt = count_stmt.where(
            CandidateProfile.experience_years <= experience_max
        )

    if salary_min is not None:
        stmt = stmt.where(CandidateProfile.salary_expectation >= salary_min)
        count_stmt = count_stmt.where(
            CandidateProfile.salary_expectation >= salary_min
        )

    if salary_max is not None:
        stmt = stmt.where(CandidateProfile.salary_expectation <= salary_max)
        count_stmt = count_stmt.where(
            CandidateProfile.salary_expectation <= salary_max
        )

    return stmt, count_stmt
