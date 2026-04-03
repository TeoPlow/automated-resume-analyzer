from __future__ import annotations

import json
from contextlib import contextmanager
from http import HTTPStatus
from typing import Any, Iterator

from libs import make_http_exception, raise_http
from libs.sqlalchemy_db import SQLAlchemyConnection, create_postgres_engine


SORT_ORDERS = {"asc", "desc"}


def _ensure_sort_order(sort_order: str) -> str:
    normalized = (sort_order or "desc").strip().lower()
    if normalized not in SORT_ORDERS:
        raise_http(
            HTTPStatus.UNPROCESSABLE_CONTENT,
            "invalid_sort_order",
            "Invalid sort_order",
            details={"sort_order": sort_order, "allowed": sorted(SORT_ORDERS)},
        )
    return normalized


class SearchRepository:
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

    def ensure_search_indexes(self) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF to_regclass('public.candidates') IS NOT NULL THEN
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_candidates_location ON candidates (location)';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_candidates_updated_at ON candidates (updated_at DESC)';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_candidates_search_tsv ON candidates USING gin (to_tsvector(''simple'', coalesce(full_name, '''') || '' '' || coalesce(email, '''') || '' '' || coalesce(location, '''')))';
                        END IF;

                        IF to_regclass('public.candidate_profiles') IS NOT NULL THEN
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_candidate_profiles_profile_gin ON candidate_profiles USING gin (profile jsonb_path_ops)';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_candidate_profiles_grade ON candidate_profiles ((lower(coalesce(profile->>''grade'', ''''))))';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_candidate_profiles_status ON candidate_profiles ((lower(coalesce(profile->>''status'', ''''))))';
                        END IF;

                        IF to_regclass('public.vacancies') IS NOT NULL THEN
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vacancies_status ON vacancies (status)';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vacancies_grade ON vacancies (grade)';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vacancies_location ON vacancies (location)';
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vacancies_search_tsv ON vacancies USING gin (to_tsvector(''simple'', coalesce(title, '''') || '' '' || coalesce(description, '''')))';
                        END IF;

                        IF to_regclass('public.vacancy_requirements') IS NOT NULL THEN
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_gin_text ON vacancy_requirements USING gin (to_tsvector(''simple'', coalesce(normalized_value, '''') || '' '' || coalesce(raw_value, '''')))';
                        END IF;

                        IF to_regclass('public.match_results') IS NOT NULL THEN
                            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_match_results_score_computed ON match_results (score DESC, computed_at DESC)';
                        END IF;
                    END $$;
                    """
                )
            conn.commit()

    @staticmethod
    def _sort_expression(sort_by: str, mapping: dict[str, str], fallback: str) -> str:
        return mapping.get(sort_by, mapping[fallback])

    @staticmethod
    def _safe_json_profile(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    def search_candidates(
        self,
        skills: list[str],
        grade: str | None,
        location: str | None,
        experience_years: float | None,
        salary: float | None,
        status: str | None,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[dict[str, Any]], int]:
        order = _ensure_sort_order(sort_order)

        sort_mapping = {
            "updated_at": "c.updated_at",
            "created_at": "c.created_at",
            "full_name": "c.full_name",
            "experience_years": "CASE WHEN coalesce(cp.profile->>'experience_years', '') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (cp.profile->>'experience_years')::numeric ELSE 0 END",
            "salary": "CASE WHEN coalesce(cp.profile->>'salary', '') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (cp.profile->>'salary')::numeric ELSE 0 END",
            "latest_match_score": "COALESCE(latest_match.score, 0)",
        }
        sort_expr = self._sort_expression(sort_by, sort_mapping, fallback="updated_at")

        where_parts: list[str] = []
        params: list[Any] = []

        if grade:
            where_parts.append("LOWER(COALESCE(cp.profile->>'grade', '')) = LOWER(%s)")
            params.append(grade)

        if location:
            where_parts.append("LOWER(COALESCE(c.location, '')) LIKE LOWER(%s)")
            params.append(f"%{location}%")

        if experience_years is not None:
            where_parts.append(
                "CASE WHEN coalesce(cp.profile->>'experience_years', '') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (cp.profile->>'experience_years')::numeric ELSE 0 END >= %s"
            )
            params.append(experience_years)

        if salary is not None:
            where_parts.append(
                "CASE WHEN coalesce(cp.profile->>'salary', '') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (cp.profile->>'salary')::numeric ELSE 0 END <= %s"
            )
            params.append(salary)

        if status:
            where_parts.append("LOWER(COALESCE(cp.profile->>'status', '')) = LOWER(%s)")
            params.append(status)

        for skill in skills:
            cleaned = skill.strip().lower()
            if not cleaned:
                continue
            where_parts.append(
                """
                (
                    EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(COALESCE(cp.profile->'skills', '[]'::jsonb)) AS s
                        WHERE LOWER(s) = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(COALESCE(cp.profile->'hard_skills', '[]'::jsonb)) AS s
                        WHERE LOWER(s) = %s
                    )
                    OR EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(COALESCE(cp.profile->'tech_stack', '[]'::jsonb)) AS s
                        WHERE LOWER(s) = %s
                    )
                    OR LOWER(COALESCE(cp.profile::text, '')) LIKE %s
                )
                """
            )
            params.extend([cleaned, cleaned, cleaned, f"%{cleaned}%"])

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        base_from = """
            FROM candidates c
            LEFT JOIN candidate_profiles cp ON cp.candidate_id = c.candidate_id
            LEFT JOIN LATERAL (
                SELECT mr.score, mr.vacancy_id, mr.computed_at
                FROM match_results mr
                WHERE mr.candidate_id = c.candidate_id
                ORDER BY mr.computed_at DESC
                LIMIT 1
            ) latest_match ON TRUE
        """

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS total {base_from} {where_sql}", tuple(params))
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

                cur.execute(
                    f"""
                    SELECT
                        c.candidate_id,
                        c.full_name,
                        c.email,
                        c.phone,
                        c.location,
                        c.source,
                        c.external_id,
                        c.created_at,
                        c.updated_at,
                        cp.profile,
                        latest_match.score AS latest_match_score,
                        latest_match.vacancy_id AS latest_match_vacancy_id,
                        latest_match.computed_at AS latest_match_computed_at
                    {base_from}
                    {where_sql}
                    ORDER BY {sort_expr} {order}
                    LIMIT %s
                    OFFSET %s
                    """,
                    tuple([*params, limit, offset]),
                )
                rows = cur.fetchall()

        for row in rows:
            row["profile"] = self._safe_json_profile(row.get("profile"))
            if row.get("latest_match_score") is not None:
                row["latest_match_score"] = float(row["latest_match_score"])
        return list(rows), total

    def search_vacancies(
        self,
        query: str | None,
        status: str | None,
        grade: str | None,
        location: str | None,
        skill: str | None,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[dict[str, Any]], int]:
        order = _ensure_sort_order(sort_order)

        sort_mapping = {
            "updated_at": "v.updated_at",
            "created_at": "v.created_at",
            "title": "v.title",
            "status": "v.status",
            "salary_from": "COALESCE(v.salary_from, 0)",
            "salary_to": "COALESCE(v.salary_to, 0)",
        }
        sort_expr = self._sort_expression(sort_by, sort_mapping, fallback="updated_at")

        where_parts: list[str] = []
        params: list[Any] = []

        if status:
            where_parts.append("LOWER(COALESCE(v.status, '')) = LOWER(%s)")
            params.append(status)

        if grade:
            where_parts.append("LOWER(COALESCE(v.grade, '')) = LOWER(%s)")
            params.append(grade)

        if location:
            where_parts.append("LOWER(COALESCE(v.location, '')) LIKE LOWER(%s)")
            params.append(f"%{location}%")

        if query:
            where_parts.append(
                "to_tsvector('simple', COALESCE(v.title, '') || ' ' || COALESCE(v.description, '')) @@ plainto_tsquery('simple', %s)"
            )
            params.append(query)

        if skill:
            where_parts.append(
                "EXISTS (SELECT 1 FROM vacancy_requirements vr2 WHERE vr2.vacancy_id = v.vacancy_id AND LOWER(vr2.normalized_value) = LOWER(%s))"
            )
            params.append(skill)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS total FROM vacancies v {where_sql}", tuple(params))
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

                cur.execute(
                    f"""
                    SELECT
                        v.vacancy_id,
                        v.title,
                        v.description,
                        v.grade,
                        v.location,
                        v.status,
                        v.salary_from,
                        v.salary_to,
                        v.currency,
                        v.created_at,
                        v.updated_at,
                        ARRAY_REMOVE(ARRAY_AGG(vr.normalized_value), NULL) AS requirements
                    FROM vacancies v
                    LEFT JOIN vacancy_requirements vr ON vr.vacancy_id = v.vacancy_id
                    {where_sql}
                    GROUP BY
                        v.vacancy_id,
                        v.title,
                        v.description,
                        v.grade,
                        v.location,
                        v.status,
                        v.salary_from,
                        v.salary_to,
                        v.currency,
                        v.created_at,
                        v.updated_at
                    ORDER BY {sort_expr} {order}
                    LIMIT %s
                    OFFSET %s
                    """,
                    tuple([*params, limit, offset]),
                )
                rows = cur.fetchall()

        for row in rows:
            row["salary_from"] = float(row["salary_from"]) if row.get("salary_from") is not None else None
            row["salary_to"] = float(row["salary_to"]) if row.get("salary_to") is not None else None
            row["requirements"] = [str(item) for item in (row.get("requirements") or [])]
        return list(rows), total

    def search_matches(
        self,
        vacancy_id: str | None,
        candidate_id: str | None,
        run_id: str | None,
        min_score: float | None,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[dict[str, Any]], int]:
        order = _ensure_sort_order(sort_order)

        sort_mapping = {
            "score": "mr.score",
            "computed_at": "mr.computed_at",
            "rank_position": "mr.rank_position",
        }
        sort_expr = self._sort_expression(sort_by, sort_mapping, fallback="score")

        where_parts: list[str] = []
        params: list[Any] = []

        if vacancy_id:
            where_parts.append("mr.vacancy_id = %s")
            params.append(vacancy_id)

        if candidate_id:
            where_parts.append("mr.candidate_id = %s")
            params.append(candidate_id)

        if run_id:
            where_parts.append("mr.run_id = %s")
            params.append(run_id)

        if min_score is not None:
            where_parts.append("mr.score >= %s")
            params.append(min_score)

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS total FROM match_results mr {where_sql}", tuple(params))
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

                cur.execute(
                    f"""
                    SELECT
                        mr.run_id,
                        mr.vacancy_id,
                        mr.candidate_id,
                        mr.score,
                        mr.rank_position,
                        mr.computed_at,
                        me.explanation
                    FROM match_results mr
                    LEFT JOIN match_explanations me
                        ON me.run_id = mr.run_id AND me.candidate_id = mr.candidate_id
                    {where_sql}
                    ORDER BY {sort_expr} {order}
                    LIMIT %s
                    OFFSET %s
                    """,
                    tuple([*params, limit, offset]),
                )
                rows = cur.fetchall()

        for row in rows:
            row["score"] = float(row["score"]) if row.get("score") is not None else 0.0
            row["explanation"] = self._safe_json_profile(row.get("explanation"))
        return list(rows), total

    def get_summary(self) -> dict[str, Any]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total_candidates FROM candidates")
                candidates_row = cur.fetchone() or {"total_candidates": 0}

                cur.execute("SELECT COUNT(*) AS total_vacancies FROM vacancies")
                vacancies_row = cur.fetchone() or {"total_vacancies": 0}

                cur.execute("SELECT COUNT(*) AS open_vacancies FROM vacancies WHERE status = 'open'")
                open_vacancies_row = cur.fetchone() or {"open_vacancies": 0}

                cur.execute("SELECT COUNT(*) AS total_matches FROM match_results")
                matches_row = cur.fetchone() or {"total_matches": 0}

                cur.execute("SELECT COUNT(*) AS total_runs FROM match_runs")
                runs_row = cur.fetchone() or {"total_runs": 0}

                cur.execute("SELECT COUNT(*) AS completed_runs FROM match_runs WHERE status = 'completed'")
                completed_runs_row = cur.fetchone() or {"completed_runs": 0}

                cur.execute(
                    """
                    SELECT AVG(score)::numeric(5, 2) AS average_score
                    FROM match_results
                    """
                )
                avg_score_row = cur.fetchone() or {"average_score": None}

        average_score = avg_score_row.get("average_score")
        return {
            "total_candidates": int(candidates_row["total_candidates"]),
            "total_vacancies": int(vacancies_row["total_vacancies"]),
            "open_vacancies": int(open_vacancies_row["open_vacancies"]),
            "total_matches": int(matches_row["total_matches"]),
            "total_runs": int(runs_row["total_runs"]),
            "completed_runs": int(completed_runs_row["completed_runs"]),
            "average_score": float(average_score) if average_score is not None else None,
        }


repository: SearchRepository | None = None


def get_repository() -> SearchRepository:
    global repository
    if repository is None:
        repository = SearchRepository()
    return repository