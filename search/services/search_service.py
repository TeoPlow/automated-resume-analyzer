from common.logger import setup_logger

from search.repository import SearchRepository
from search.schemas.search import (
    CandidateSearchData,
    GradeCount,
    LocationCount,
    MatchSearchData,
    SkillCount,
    SummaryData,
    VacancySearchData,
)

logger = setup_logger("search.service")


class SearchService:
    """Поиск и агрегация данных из всех таблиц системы."""

    async def search_candidates(
        self,
        repo: SearchRepository,
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
    ) -> tuple[list[CandidateSearchData], int]:
        """Поиск кандидатов с фильтрами."""
        rows, total = await repo.search_candidates(
            q=q, skills=skills, grade=grade, location=location,
            experience_min=experience_min, experience_max=experience_max,
            salary_min=salary_min, salary_max=salary_max,
            limit=limit, offset=offset,
        )
        data = [_to_candidate_data(cand, prof) for cand, prof in rows]
        return data, total

    async def search_vacancies(
        self,
        repo: SearchRepository,
        status: str | None = None,
        department: str | None = None,
        grade: str | None = None,
        location: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[VacancySearchData], int]:
        """Поиск вакансий с фильтрами."""
        vacancies, total = await repo.search_vacancies(
            status=status, department=department,
            grade=grade, location=location,
            limit=limit, offset=offset,
        )
        data = [_to_vacancy_data(v) for v in vacancies]
        return data, total

    async def search_matches(
        self,
        repo: SearchRepository,
        vacancy_id: str | None = None,
        min_score: float | None = None,
        grade: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[MatchSearchData], int]:
        """Поиск результатов матчинга."""
        rows, total = await repo.search_matches(
            vacancy_id=vacancy_id, min_score=min_score,
            grade=grade, limit=limit, offset=offset,
        )
        data = [_to_match_data(mr, cand, vac) for mr, cand, vac in rows]
        return data, total

    async def get_summary(
        self, repo: SearchRepository
    ) -> SummaryData:
        """Получить агрегированную статистику."""
        raw = await repo.get_summary()
        return SummaryData(
            total_candidates=raw["total_candidates"],
            total_vacancies=raw["total_vacancies"],
            total_matches=raw["total_matches"],
            grades=[GradeCount(**g) for g in raw["grades"]],
            top_skills=[SkillCount(**s) for s in raw["top_skills"]],
            locations=[LocationCount(**l) for l in raw["locations"]],
        )


def _to_candidate_data(candidate, profile) -> CandidateSearchData:
    """Преобразовать ORM-объекты кандидата и профиля в схему."""
    return CandidateSearchData(
        id=str(candidate.id),
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        skills=profile.skills if profile else [],
        grade=profile.grade if profile else None,
        location=profile.location if profile else None,
        experience_years=float(profile.experience_years) if profile and profile.experience_years else None,
        salary_expectation=profile.salary_expectation if profile else None,
    )

def _to_vacancy_data(vacancy) -> VacancySearchData:
    """Преобразовать ORM-модель вакансии в схему поиска."""
    return VacancySearchData(
        id=str(vacancy.id),
        title=vacancy.title,
        department=vacancy.department,
        location=vacancy.location,
        grade=vacancy.grade or [],
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        status=vacancy.status,
        requirements_count=len(vacancy.requirements) if vacancy.requirements else 0,
    )

def _to_match_data(match_result, candidate, vacancy) -> MatchSearchData:
    """Преобразовать результат матчинга в схему поиска."""
    return MatchSearchData(
        candidate_id=str(match_result.candidate_id),
        candidate_name=candidate.full_name,
        vacancy_id=str(match_result.vacancy_id),
        vacancy_title=vacancy.title,
        final_score=float(match_result.final_score),
        skill_score=float(match_result.skill_score),
        experience_score=float(match_result.experience_score),
        grade_score=float(match_result.grade_score),
        location_score=float(match_result.location_score),
        salary_score=float(match_result.salary_score),
        rank=match_result.rank,
    )
