from __future__ import annotations

from pydantic import BaseModel


class ResumeUploadData(BaseModel):
    """Ответ на успешную загрузку резюме."""

    resume_id: str
    candidate_id: str | None = None
    status: str = "uploaded"


class ParsedContacts(BaseModel):
    """Контактные данные, извлечённые из резюме."""

    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    linkedin: str | None = None


class ExperienceItem(BaseModel):
    """Запись об опыте работы."""

    company: str
    position: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    technologies: list[str] = []


class EducationItem(BaseModel):
    """Запись об образовании."""

    institution: str
    degree: str | None = None
    field: str | None = None
    graduation_year: int | None = None


class LanguageItem(BaseModel):
    """Запись о владении языком."""

    language: str
    level: str | None = None


class ParsedData(BaseModel):
    """Полный результат парсинга резюме (LLM + regex)."""

    full_name: str | None = None
    contacts: ParsedContacts = ParsedContacts()
    location: str | None = None
    summary: str | None = None
    skills: list[str] = []
    experience: list[ExperienceItem] = []
    education: list[EducationItem] = []
    languages: list[LanguageItem] = []
    total_experience_years: float | None = None
    desired_salary: int | None = None
    desired_position: str | None = None


class ResumeData(BaseModel):
    """Данные резюме для ответа API."""

    id: str
    file_key: str
    source: str
    external_id: str | None = None
    status: str
    parsed_data: ParsedData | None = None
    error_detail: str | None = None
    created_at: str
