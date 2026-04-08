from __future__ import annotations

from pydantic import BaseModel


class CandidateProfileData(BaseModel):
    """Агрегированный профиль кандидата."""

    skills: list[str] = []
    grade: str | None = None
    location: str | None = None
    experience_years: float | None = None
    salary_expectation: int | None = None
    data: dict = {}


class CandidateData(BaseModel):
    """Полные данные кандидата для ответа API."""

    id: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    created_at: str
    updated_at: str
    profile: CandidateProfileData | None = None


class CandidateUpdateRequest(BaseModel):
    """Запрос на обновление данных кандидата."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None


class CandidateBulkRequest(BaseModel):
    """Запрос для массового получения кандидатов."""

    candidate_ids: list[str]
