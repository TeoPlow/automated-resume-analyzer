from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Any, Iterator

from libs import make_http_exception
from libs.sqlalchemy_db import SQLAlchemyConnection, create_postgres_engine


def normalize_requirements(requirements: list[str]) -> list[dict[str, str]]:
    normalized_items: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw_value in requirements:
        cleaned = " ".join(raw_value.split()).strip()
        if not cleaned:
            continue

        normalized = cleaned.lower()
        if normalized in seen:
            continue

        seen.add(normalized)
        normalized_items.append({"raw": cleaned, "normalized": normalized})

    return normalized_items


class VacancyRepository:
    def __init__(self) -> None:
        try:
            self._engine = create_postgres_engine(default_host="postgres")
        except ModuleNotFoundError as exc:
            raise make_http_exception(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="missing_dependency",
                message="SQLAlchemy PostgreSQL dependencies are not installed",
                details={"dependency": str(exc.name)},
            ) from exc
        except ValueError as exc:
            raise make_http_exception(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="invalid_database_config",
                message="Invalid PostgreSQL configuration",
                details={"exception": exc.__class__.__name__},
            ) from exc

    @contextmanager
    def _connection(self) -> Iterator[SQLAlchemyConnection]:
        try:
            connection = SQLAlchemyConnection(self._engine.connect())
        except Exception as exc:
            raise make_http_exception(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                code="database_unavailable",
                message="Cannot connect to PostgreSQL",
                details={"exception": exc.__class__.__name__},
            ) from exc

        try:
            yield connection
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vacancies (
                        vacancy_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        grade TEXT,
                        location TEXT,
                        status TEXT NOT NULL,
                        salary_from NUMERIC(12, 2),
                        salary_to NUMERIC(12, 2),
                        currency TEXT,
                        created_by_actor_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vacancy_requirements (
                        requirement_id BIGSERIAL PRIMARY KEY,
                        vacancy_id TEXT NOT NULL REFERENCES vacancies(vacancy_id) ON DELETE CASCADE,
                        requirement_type TEXT NOT NULL DEFAULT 'skill',
                        raw_value TEXT NOT NULL,
                        normalized_value TEXT NOT NULL,
                        weight NUMERIC(5, 2) NOT NULL DEFAULT 1.0
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_vacancy_id
                    ON vacancy_requirements (vacancy_id)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_normalized
                    ON vacancy_requirements (normalized_value)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_vacancies_status_updated_at
                    ON vacancies (status, updated_at DESC)
                    """
                )
            conn.commit()

    def create_vacancy(
        self,
        vacancy_id: str,
        title: str,
        description: str | None,
        grade: str | None,
        location: str | None,
        status: str,
        salary_from: float | None,
        salary_to: float | None,
        currency: str | None,
        requirements: list[dict[str, str]],
        created_by_actor_id: str,
    ) -> dict[str, Any]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
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
                        created_by_actor_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
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
                    ),
                )

                self._insert_requirements(cur, vacancy_id, requirements)
            conn.commit()

        created = self.get_vacancy(vacancy_id)
        if created is None:
            raise make_http_exception(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="vacancy_create_failed",
                message="Vacancy was created but cannot be loaded",
                details={"vacancy_id": vacancy_id},
            )
        return created

    @staticmethod
    def _insert_requirements(cur: Any, vacancy_id: str, requirements: list[dict[str, str]]) -> None:
        for requirement in requirements:
            cur.execute(
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
                (vacancy_id, requirement["raw"], requirement["normalized"]),
            )

    def get_vacancy(self, vacancy_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
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
                        created_at,
                        updated_at
                    FROM vacancies
                    WHERE vacancy_id = %s
                    LIMIT 1
                    """,
                    (vacancy_id,),
                )
                vacancy_row = cur.fetchone()
                if vacancy_row is None:
                    return None

                cur.execute(
                    """
                    SELECT raw_value, normalized_value
                    FROM vacancy_requirements
                    WHERE vacancy_id = %s
                    ORDER BY requirement_id ASC
                    """,
                    (vacancy_id,),
                )
                requirement_rows = cur.fetchall()

        vacancy_row["requirements"] = [
            {
                "raw": str(item["raw_value"]),
                "normalized": str(item["normalized_value"]),
            }
            for item in requirement_rows
        ]
        return vacancy_row

    def update_vacancy(
        self,
        vacancy_id: str,
        title: str | None,
        description: str | None,
        grade: str | None,
        location: str | None,
        status: str | None,
        salary_from: float | None,
        salary_to: float | None,
        currency: str | None,
        requirements: list[dict[str, str]] | None,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        vacancy_id,
                        title,
                        description,
                        grade,
                        location,
                        status,
                        salary_from,
                        salary_to,
                        currency
                    FROM vacancies
                    WHERE vacancy_id = %s
                    LIMIT 1
                    """,
                    (vacancy_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    return None

                next_title = title if title is not None else existing.get("title")
                next_description = description if description is not None else existing.get("description")
                next_grade = grade if grade is not None else existing.get("grade")
                next_location = location if location is not None else existing.get("location")
                next_status = status if status is not None else existing.get("status")
                next_salary_from = salary_from if salary_from is not None else existing.get("salary_from")
                next_salary_to = salary_to if salary_to is not None else existing.get("salary_to")
                next_currency = currency if currency is not None else existing.get("currency")

                cur.execute(
                    """
                    UPDATE vacancies
                    SET
                        title = %s,
                        description = %s,
                        grade = %s,
                        location = %s,
                        status = %s,
                        salary_from = %s,
                        salary_to = %s,
                        currency = %s,
                        updated_at = NOW()
                    WHERE vacancy_id = %s
                    """,
                    (
                        next_title,
                        next_description,
                        next_grade,
                        next_location,
                        next_status,
                        next_salary_from,
                        next_salary_to,
                        next_currency,
                        vacancy_id,
                    ),
                )

                if requirements is not None:
                    cur.execute("DELETE FROM vacancy_requirements WHERE vacancy_id = %s", (vacancy_id,))
                    self._insert_requirements(cur, vacancy_id, requirements)

            conn.commit()

        return self.get_vacancy(vacancy_id)

    def list_vacancies(
        self,
        limit: int,
        offset: int,
        status: str | None,
        location: str | None,
        grade: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        where_parts: list[str] = []
        params: list[Any] = []

        if status:
            where_parts.append("status = %s")
            params.append(status)
        if location:
            where_parts.append("location = %s")
            params.append(location)
        if grade:
            where_parts.append("grade = %s")
            params.append(grade)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS total FROM vacancies {where_sql}", tuple(params))
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

                cur.execute(
                    f"""
                    SELECT
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
                        created_at,
                        updated_at
                    FROM vacancies
                    {where_sql}
                    ORDER BY updated_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    tuple([*params, limit, offset]),
                )
                rows = cur.fetchall()

                vacancy_ids = [str(row["vacancy_id"]) for row in rows]
                requirements_map: dict[str, list[dict[str, str]]] = {vacancy_id: [] for vacancy_id in vacancy_ids}
                if vacancy_ids:
                    placeholders = ", ".join(["%s"] * len(vacancy_ids))
                    cur.execute(
                        f"""
                        SELECT vacancy_id, raw_value, normalized_value
                        FROM vacancy_requirements
                        WHERE vacancy_id IN ({placeholders})
                        ORDER BY requirement_id ASC
                        """,
                        tuple(vacancy_ids),
                    )
                    requirement_rows = cur.fetchall()
                    for item in requirement_rows:
                        vacancy_id = str(item["vacancy_id"])
                        requirements_map.setdefault(vacancy_id, []).append(
                            {
                                "raw": str(item["raw_value"]),
                                "normalized": str(item["normalized_value"]),
                            }
                        )

        results: list[dict[str, Any]] = []
        for row in rows:
            row["requirements"] = requirements_map.get(str(row["vacancy_id"]), [])
            results.append(row)
        return results, total

    def bulk_get_vacancies(self, vacancy_ids: list[str]) -> list[dict[str, Any]]:
        if not vacancy_ids:
            return []

        placeholders = ", ".join(["%s"] * len(vacancy_ids))
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
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
                        created_at,
                        updated_at
                    FROM vacancies
                    WHERE vacancy_id IN ({placeholders})
                    """,
                    tuple(vacancy_ids),
                )
                rows = cur.fetchall()

                cur.execute(
                    f"""
                    SELECT vacancy_id, raw_value, normalized_value
                    FROM vacancy_requirements
                    WHERE vacancy_id IN ({placeholders})
                    ORDER BY requirement_id ASC
                    """,
                    tuple(vacancy_ids),
                )
                requirement_rows = cur.fetchall()

        requirements_map: dict[str, list[dict[str, str]]] = {}
        for item in requirement_rows:
            vacancy_id = str(item["vacancy_id"])
            requirements_map.setdefault(vacancy_id, []).append(
                {
                    "raw": str(item["raw_value"]),
                    "normalized": str(item["normalized_value"]),
                }
            )

        results: list[dict[str, Any]] = []
        for row in rows:
            row["requirements"] = requirements_map.get(str(row["vacancy_id"]), [])
            results.append(row)
        return results


repository: VacancyRepository | None = None


def get_repository() -> VacancyRepository:
    global repository
    if repository is None:
        repository = VacancyRepository()
    return repository