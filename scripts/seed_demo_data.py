import asyncio
import os
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import Database
from matching.models.match import MatchExplanation, MatchResult, MatchRun
from profile.models.candidate import Candidate, CandidateProfile, Resume
from vacancy.models.vacancy import Vacancy, VacancyRequirement

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://app_user:app_password@postgres:5432/resume_analyzer"
)


def _candidate_seed_data() -> list[dict[str, Any]]:
    return [
        {
            "full_name": "Ivan Petrov",
            "email": "ivan.petrov@example.com",
            "phone": "+79990000001",
            "grade": "middle",
            "location": "Moscow",
            "experience_years": 4.0,
            "salary_expectation": 230000,
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
            "desired_position": "Backend Developer",
            "summary": "Backend engineer with production microservices experience.",
        },
        {
            "full_name": "Anna Smirnova",
            "email": "anna.smirnova@example.com",
            "phone": "+79990000002",
            "grade": "senior",
            "location": "Saint Petersburg",
            "experience_years": 7.5,
            "salary_expectation": 340000,
            "skills": ["Python", "Django", "Kubernetes", "Kafka", "AWS"],
            "desired_position": "Senior Backend Developer",
            "summary": "Senior backend developer and team lead for platform teams.",
        },
        {
            "full_name": "Pavel Sidorov",
            "email": "pavel.sidorov@example.com",
            "phone": "+79990000003",
            "grade": "junior",
            "location": "Kazan",
            "experience_years": 1.5,
            "salary_expectation": 140000,
            "skills": ["Python", "Flask", "SQL", "Git", "Linux"],
            "desired_position": "Junior Backend Developer",
            "summary": (
                "Junior engineer with strong motivation and API "
                "development practice."
            ),
        },
        {
            "full_name": "Maria Volkova",
            "email": "maria.volkova@example.com",
            "phone": "+79990000004",
            "grade": "middle",
            "location": "Novosibirsk",
            "experience_years": 3.2,
            "salary_expectation": 210000,
            "skills": ["JavaScript", "TypeScript", "React", "Node.js", "Docker"],
            "desired_position": "Fullstack Developer",
            "summary": "Fullstack engineer focused on React and Node.js products.",
        },
        {
            "full_name": "Dmitry Kozlov",
            "email": "dmitry.kozlov@example.com",
            "phone": "+79990000005",
            "grade": "lead",
            "location": "Moscow",
            "experience_years": 10.0,
            "salary_expectation": 460000,
            "skills": ["Python", "Go", "Architecture", "Kubernetes", "Mentoring"],
            "desired_position": "Engineering Lead",
            "summary": "Engineering lead with extensive system design experience.",
        },
    ]


def _vacancy_seed_data() -> list[dict[str, Any]]:
    return [
        {
            "title": "Python Backend Developer",
            "description": "Build and maintain backend APIs for recruitment products.",
            "department": "Platform",
            "location": "Moscow",
            "grade": ["middle", "senior"],
            "salary_min": 220000,
            "salary_max": 360000,
            "status": "open",
            "requirements": [
                {
                    "skill": "Python",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 3.0,
                },
                {
                    "skill": "FastAPI",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 2.0,
                },
                {
                    "skill": "PostgreSQL",
                    "category": "hard",
                    "priority": "preferred",
                    "min_experience_years": 2.0,
                },
                {
                    "skill": "Docker",
                    "category": "tool",
                    "priority": "preferred",
                    "min_experience_years": 1.0,
                },
            ],
        },
        {
            "title": "Frontend Developer (React)",
            "description": "Develop UI modules for HR dashboard and analytics screens.",
            "department": "Product",
            "location": "Remote",
            "grade": ["junior", "middle"],
            "salary_min": 150000,
            "salary_max": 260000,
            "status": "open",
            "requirements": [
                {
                    "skill": "React",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 1.5,
                },
                {
                    "skill": "TypeScript",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 1.0,
                },
                {
                    "skill": "Node.js",
                    "category": "hard",
                    "priority": "nice_to_have",
                    "min_experience_years": 1.0,
                },
                {
                    "skill": "Docker",
                    "category": "tool",
                    "priority": "nice_to_have",
                    "min_experience_years": None,
                },
            ],
        },
        {
            "title": "Data Engineer",
            "description": (
                "Build ETL pipelines and analytical data marts " "for hiring metrics."
            ),
            "department": "Data",
            "location": "Saint Petersburg",
            "grade": ["middle", "senior"],
            "salary_min": 250000,
            "salary_max": 380000,
            "status": "draft",
            "requirements": [
                {
                    "skill": "SQL",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 3.0,
                },
                {
                    "skill": "Airflow",
                    "category": "tool",
                    "priority": "preferred",
                    "min_experience_years": 1.0,
                },
                {
                    "skill": "Python",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 2.0,
                },
                {
                    "skill": "Kafka",
                    "category": "tool",
                    "priority": "nice_to_have",
                    "min_experience_years": None,
                },
            ],
        },
        {
            "title": "DevOps Engineer",
            "description": (
                "Improve CI/CD, observability and container " "platform reliability."
            ),
            "department": "Infrastructure",
            "location": "Moscow",
            "grade": ["middle", "senior", "lead"],
            "salary_min": 270000,
            "salary_max": 420000,
            "status": "open",
            "requirements": [
                {
                    "skill": "Kubernetes",
                    "category": "tool",
                    "priority": "required",
                    "min_experience_years": 2.0,
                },
                {
                    "skill": "CI/CD",
                    "category": "hard",
                    "priority": "required",
                    "min_experience_years": 2.0,
                },
                {
                    "skill": "Docker",
                    "category": "tool",
                    "priority": "required",
                    "min_experience_years": 2.0,
                },
                {
                    "skill": "Linux",
                    "category": "hard",
                    "priority": "preferred",
                    "min_experience_years": 2.0,
                },
            ],
        },
    ]


async def _reset_tables(session: AsyncSession) -> None:
    # Reset dependent tables first to satisfy foreign keys.
    for model in (
        MatchExplanation,
        MatchResult,
        MatchRun,
        Resume,
        CandidateProfile,
        Candidate,
        VacancyRequirement,
        Vacancy,
    ):
        await session.execute(delete(model))


def _build_candidate(seed: dict[str, Any]) -> Candidate:
    candidate = Candidate(
        full_name=seed["full_name"],
        email=seed["email"],
        phone=seed["phone"],
    )

    candidate.profile = CandidateProfile(
        skills=seed["skills"],
        grade=seed["grade"],
        location=seed["location"],
        experience_years=seed["experience_years"],
        salary_expectation=seed["salary_expectation"],
        data={
            "skills": seed["skills"],
            "location": seed["location"],
            "desired_position": seed["desired_position"],
            "summary": seed["summary"],
            "total_experience_years": seed["experience_years"],
            "languages": [
                {"language": "English", "level": "B2"},
                {"language": "Russian", "level": "Native"},
            ],
            "experience": [],
            "education": [],
        },
    )

    candidate.resumes = [
        Resume(
            file_key=f"demo/{seed['full_name'].lower().replace(' ', '_')}.pdf",
            source="web",
            status="parsed",
            raw_text=f"Demo resume for {seed['full_name']}",
            parsed_data={
                "full_name": seed["full_name"],
                "skills": seed["skills"],
                "location": seed["location"],
                "summary": seed["summary"],
                "total_experience_years": seed["experience_years"],
                "desired_salary": seed["salary_expectation"],
                "desired_position": seed["desired_position"],
                "contacts": {
                    "email": seed["email"],
                    "phone": seed["phone"],
                },
                "experience": [],
                "education": [],
                "languages": [
                    {"language": "English", "level": "B2"},
                    {"language": "Russian", "level": "Native"},
                ],
            },
        )
    ]

    return candidate


def _build_vacancy(seed: dict[str, Any]) -> Vacancy:
    vacancy = Vacancy(
        title=seed["title"],
        description=seed["description"],
        department=seed["department"],
        location=seed["location"],
        grade=seed["grade"],
        salary_min=seed["salary_min"],
        salary_max=seed["salary_max"],
        status=seed["status"],
    )

    vacancy.requirements = [
        VacancyRequirement(
            skill=req["skill"],
            category=req["category"],
            priority=req["priority"],
            min_experience_years=req["min_experience_years"],
        )
        for req in seed["requirements"]
    ]

    return vacancy


async def _count_rows(session: AsyncSession, model) -> int:
    result = await session.execute(select(func.count(model.id)))
    return int(result.scalar() or 0)


async def seed_demo_data() -> None:
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    db = Database(url=database_url, echo=False)

    await db.create_tables()

    async with db.session() as session:
        await _reset_tables(session)

        candidates = [_build_candidate(item) for item in _candidate_seed_data()]
        vacancies = [_build_vacancy(item) for item in _vacancy_seed_data()]

        session.add_all(candidates)
        session.add_all(vacancies)
        await session.commit()

        candidate_count = await _count_rows(session, Candidate)
        vacancy_count = await _count_rows(session, Vacancy)

    await db.dispose()

    print("Seed completed: " f"{candidate_count} candidates, {vacancy_count} vacancies")


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
