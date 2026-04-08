from __future__ import annotations

from pydantic import BaseModel


class RequirementRequest(BaseModel):
    """Требование к навыку при создании/обновлении вакансии."""

    skill: str
    category: str = "hard"
    priority: str = "required"
    min_experience_years: float | None = None


class VacancyCreateRequest(BaseModel):
    """Запрос на создание вакансии."""

    title: str
    description: str
    department: str | None = None
    location: str
    grade: list[str]
    salary_min: int | None = None
    salary_max: int | None = None
    requirements: list[RequirementRequest] = []


class VacancyUpdateRequest(BaseModel):
    """Запрос на обновление вакансии (все поля опциональны)."""

    title: str | None = None
    description: str | None = None
    department: str | None = None
    location: str | None = None
    grade: list[str] | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    status: str | None = None
    requirements: list[RequirementRequest] | None = None


class RequirementData(BaseModel):
    """Данные требования для ответа API."""

    id: str
    skill: str
    category: str
    priority: str
    min_experience_years: float | None = None


class VacancyData(BaseModel):
    """Полные данные вакансии для ответа API."""

    id: str
    title: str
    description: str
    department: str | None = None
    location: str
    grade: list[str]
    salary_min: int | None = None
    salary_max: int | None = None
    status: str
    requirements: list[RequirementData] = []
    created_at: str
    updated_at: str


class VacancyBulkRequest(BaseModel):
    """Запрос для массового получения вакансий."""

    vacancy_ids: list[str]
