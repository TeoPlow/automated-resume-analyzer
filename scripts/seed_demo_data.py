from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


logger = logging.getLogger(__name__)

def _build_engine() -> Engine:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    dbname = os.getenv("POSTGRES_DB", "resume_analyzer")
    user = os.getenv("POSTGRES_USER", "app_user")
    password = os.getenv("POSTGRES_PASSWORD", "app_password")
    sslmode = os.getenv("POSTGRES_SSLMODE", "prefer")
    url = URL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=dbname,
        query={"sslmode": sslmode},
    )
    return create_engine(url, pool_pre_ping=True)


def seed_demo_data() -> None:
    engine = _build_engine()

    candidates = [
        {
            "candidate_id": "demo_cand_1",
            "source": "portal",
            "external_id": "demo-ext-1",
            "full_name": "Ivan Petrov",
            "email": "ivan.petrov@example.com",
            "phone": "+79990001122",
            "location": "Moscow",
            "profile": {
                "grade": "middle",
                "status": "active",
                "experience_years": 4,
                "salary": 220000,
                "skills": ["python", "fastapi", "postgresql", "docker"],
            },
        },
        {
            "candidate_id": "demo_cand_2",
            "source": "telegram",
            "external_id": "demo-ext-2",
            "full_name": "Anna Sidorova",
            "email": "anna.sidorova@example.com",
            "phone": "+79990003344",
            "location": "Saint Petersburg",
            "profile": {
                "grade": "senior",
                "status": "active",
                "experience_years": 7,
                "salary": 320000,
                "skills": ["python", "sql", "kubernetes", "aws", "rabbitmq"],
            },
        },
    ]

    vacancy = {
        "vacancy_id": "demo_vac_1",
        "title": "Backend Python Engineer",
        "description": "Build microservices on FastAPI and PostgreSQL",
        "grade": "middle",
        "location": "Moscow",
        "status": "open",
        "salary_from": 180000,
        "salary_to": 280000,
        "currency": "RUB",
        "created_by_actor_id": "u_admin",
        "requirements": [
            {"raw": "Python", "normalized": "python"},
            {"raw": "FastAPI", "normalized": "fastapi"},
            {"raw": "PostgreSQL", "normalized": "postgresql"},
        ],
    }

    run_id = "demo_run_1"

    with engine.connect() as conn:
        for candidate in candidates:
            conn.exec_driver_sql(
                """
                INSERT INTO candidates (
                    candidate_id,
                    source,
                    external_id,
                    full_name,
                    email,
                    phone,
                    location,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (candidate_id)
                DO UPDATE SET
                    source = EXCLUDED.source,
                    external_id = EXCLUDED.external_id,
                    full_name = EXCLUDED.full_name,
                    email = EXCLUDED.email,
                    phone = EXCLUDED.phone,
                    location = EXCLUDED.location,
                    updated_at = NOW()
                """,
                (
                    candidate["candidate_id"],
                    candidate["source"],
                    candidate["external_id"],
                    candidate["full_name"],
                    candidate["email"],
                    candidate["phone"],
                    candidate["location"],
                ),
            )

            conn.exec_driver_sql(
                """
                INSERT INTO candidate_profiles (candidate_id, profile, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (candidate_id)
                DO UPDATE SET profile = EXCLUDED.profile, updated_at = NOW()
                """,
                (candidate["candidate_id"], json.dumps(candidate["profile"])),
            )

        conn.exec_driver_sql(
            """
            INSERT INTO vacancies (
                vacancy_id,
                title,
                description,
                grade,
                location,
                status,
                salary_from,
                salary_to,
                currency,
                created_by_actor_id,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (vacancy_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                grade = EXCLUDED.grade,
                location = EXCLUDED.location,
                status = EXCLUDED.status,
                salary_from = EXCLUDED.salary_from,
                salary_to = EXCLUDED.salary_to,
                currency = EXCLUDED.currency,
                created_by_actor_id = EXCLUDED.created_by_actor_id,
                updated_at = NOW()
            """,
            (
                vacancy["vacancy_id"],
                vacancy["title"],
                vacancy["description"],
                vacancy["grade"],
                vacancy["location"],
                vacancy["status"],
                vacancy["salary_from"],
                vacancy["salary_to"],
                vacancy["currency"],
                vacancy["created_by_actor_id"],
            ),
        )

        conn.exec_driver_sql("DELETE FROM vacancy_requirements WHERE vacancy_id = %s", (vacancy["vacancy_id"],))
        for requirement in vacancy["requirements"]:
            conn.exec_driver_sql(
                """
                INSERT INTO vacancy_requirements (
                    vacancy_id,
                    requirement_type,
                    raw_value,
                    normalized_value,
                    weight
                )
                VALUES (%s, 'skill', %s, %s, 1.0)
                """,
                (vacancy["vacancy_id"], requirement["raw"], requirement["normalized"]),
            )

        conn.exec_driver_sql(
            """
            INSERT INTO match_runs (
                run_id,
                vacancy_id,
                initiated_by_actor_id,
                top_k,
                force_recompute,
                status,
                created_at,
                completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (run_id)
            DO UPDATE SET
                vacancy_id = EXCLUDED.vacancy_id,
                initiated_by_actor_id = EXCLUDED.initiated_by_actor_id,
                top_k = EXCLUDED.top_k,
                force_recompute = EXCLUDED.force_recompute,
                status = EXCLUDED.status,
                completed_at = NOW()
            """,
            (run_id, vacancy["vacancy_id"], "u_admin", 10, False, "completed"),
        )

        conn.exec_driver_sql("DELETE FROM match_results WHERE run_id = %s", (run_id,))
        conn.exec_driver_sql("DELETE FROM match_explanations WHERE run_id = %s", (run_id,))

        match_rows = [
            ("demo_cand_1", 100.0, 1, {"matched_requirements": ["python", "fastapi", "postgresql"]}),
            ("demo_cand_2", 33.33, 2, {"matched_requirements": ["python"]}),
        ]
        now = datetime.now(UTC)
        for candidate_id, score, rank_position, explanation in match_rows:
            conn.exec_driver_sql(
                """
                INSERT INTO match_results (
                    run_id,
                    vacancy_id,
                    candidate_id,
                    score,
                    rank_position,
                    computed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (run_id, vacancy["vacancy_id"], candidate_id, score, rank_position, now),
            )
            conn.exec_driver_sql(
                """
                INSERT INTO match_explanations (run_id, candidate_id, explanation, created_at)
                VALUES (%s, %s, %s::jsonb, %s)
                """,
                (run_id, candidate_id, json.dumps(explanation), now),
            )

        conn.commit()

    logger.info("Demo data seeded successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seed_demo_data()
