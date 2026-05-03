from __future__ import annotations

from pydantic import BaseModel


class MatchWeights(BaseModel):
    """Веса факторов скоринга (сумма = 1.0)."""

    skills: float = 0.40
    experience: float = 0.25
    grade: float = 0.15
    location: float = 0.10
    salary: float = 0.10


class MatchRunRequest(BaseModel):
    """Запрос на запуск матчинга."""

    vacancy_id: str
    candidate_ids: list[str] | None = None
    top_k: int | None = None
    force_recompute: bool = False
    weights: MatchWeights | None = None


class MatchRunData(BaseModel):
    """Ответ на запуск матчинга."""

    run_id: str
    status: str = "running"


class ExplanationData(BaseModel):
    """Пояснение к оценке по одному фактору."""

    factor: str
    detail: str
    score: float
    weight: float
    impact: float


class MatchResultData(BaseModel):
    """Результат матчинга для одного кандидата."""

    id: str
    candidate_id: str
    candidate_name: str | None = None
    vacancy_id: str
    vacancy_title: str | None = None
    final_score: float
    skill_score: float
    experience_score: float
    grade_score: float
    location_score: float
    salary_score: float
    rank: int
    explanations: list[ExplanationData] = []
