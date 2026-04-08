from pydantic import BaseModel


class CandidateSearchData(BaseModel):
    """Результат поиска кандидата."""

    id: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    skills: list[str] = []
    grade: str | None = None
    location: str | None = None
    experience_years: float | None = None
    salary_expectation: int | None = None


class VacancySearchData(BaseModel):
    """Результат поиска вакансии."""

    id: str
    title: str
    department: str | None = None
    location: str
    grade: list[str] = []
    salary_min: int | None = None
    salary_max: int | None = None
    status: str
    requirements_count: int = 0


class MatchSearchData(BaseModel):
    """Результат поиска матча (кандидат + скор)."""

    candidate_id: str
    candidate_name: str
    vacancy_id: str
    vacancy_title: str
    final_score: float
    skill_score: float
    experience_score: float
    grade_score: float
    location_score: float
    salary_score: float
    rank: int


class GradeCount(BaseModel):
    """Статистика по грейдам."""

    grade: str
    count: int


class SkillCount(BaseModel):
    """Статистика по навыкам."""

    skill: str
    count: int


class LocationCount(BaseModel):
    """Статистика по локациям."""

    location: str
    count: int


class SummaryData(BaseModel):
    """Агрегированная статистика."""

    total_candidates: int = 0
    total_vacancies: int = 0
    total_matches: int = 0
    grades: list[GradeCount] = []
    top_skills: list[SkillCount] = []
    locations: list[LocationCount] = []
