from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Any, Iterator

from libs import make_http_exception
from libs.sqlalchemy_db import SQLAlchemyConnection, create_postgres_engine


class MatchingRepository:
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
                    CREATE TABLE IF NOT EXISTS match_runs (
                        run_id TEXT PRIMARY KEY,
                        vacancy_id TEXT NOT NULL,
                        initiated_by_actor_id TEXT,
                        top_k INTEGER NOT NULL,
                        force_recompute BOOLEAN NOT NULL DEFAULT FALSE,
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        completed_at TIMESTAMPTZ
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_match_runs_vacancy_created_at
                    ON match_runs (vacancy_id, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS match_results (
                        match_result_id BIGSERIAL PRIMARY KEY,
                        run_id TEXT NOT NULL REFERENCES match_runs(run_id) ON DELETE CASCADE,
                        vacancy_id TEXT NOT NULL,
                        candidate_id TEXT NOT NULL,
                        score NUMERIC(5, 2) NOT NULL,
                        rank_position INTEGER NOT NULL,
                        computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_match_results_run_rank
                    ON match_results (run_id, rank_position ASC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_match_results_vacancy_score
                    ON match_results (vacancy_id, score DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_match_results_candidate_score
                    ON match_results (candidate_id, score DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS match_explanations (
                        explanation_id BIGSERIAL PRIMARY KEY,
                        run_id TEXT NOT NULL REFERENCES match_runs(run_id) ON DELETE CASCADE,
                        candidate_id TEXT NOT NULL,
                        explanation JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_match_explanations_run_candidate
                    ON match_explanations (run_id, candidate_id)
                    """
                )
            conn.commit()

    def create_run(
        self,
        run_id: str,
        vacancy_id: str,
        initiated_by_actor_id: str,
        top_k: int,
        force_recompute: bool,
        status: str,
    ) -> dict[str, Any]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO match_runs (
                        run_id,
                        vacancy_id,
                        initiated_by_actor_id,
                        top_k,
                        force_recompute,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, vacancy_id, initiated_by_actor_id, top_k, force_recompute, status),
                )
            conn.commit()
        return self.get_run(run_id) or {}

    def complete_run(self, run_id: str, status: str) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE match_runs
                    SET status = %s, completed_at = NOW()
                    WHERE run_id = %s
                    """,
                    (status, run_id),
                )
            conn.commit()

    def save_run_results(
        self,
        run_id: str,
        vacancy_id: str,
        results: list[dict[str, Any]],
    ) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM match_results WHERE run_id = %s", (run_id,))
                cur.execute("DELETE FROM match_explanations WHERE run_id = %s", (run_id,))

                for index, item in enumerate(results, start=1):
                    cur.execute(
                        """
                        INSERT INTO match_results (
                            run_id,
                            vacancy_id,
                            candidate_id,
                            score,
                            rank_position
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            run_id,
                            vacancy_id,
                            item["candidate_id"],
                            float(item["score"]),
                            index,
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO match_explanations (run_id, candidate_id, explanation)
                        VALUES (%s, %s, %s::jsonb)
                        """,
                        (
                            run_id,
                            item["candidate_id"],
                            json.dumps(item.get("explanation") or {}),
                        ),
                    )
            conn.commit()

    @staticmethod
    def _normalize_explanation(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        run_id,
                        vacancy_id,
                        initiated_by_actor_id,
                        top_k,
                        force_recompute,
                        status,
                        created_at,
                        completed_at
                    FROM match_runs
                    WHERE run_id = %s
                    LIMIT 1
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
        return row

    def get_results_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        r.candidate_id,
                        r.vacancy_id,
                        r.score,
                        r.rank_position,
                        r.computed_at,
                        e.explanation
                    FROM match_results r
                    LEFT JOIN match_explanations e
                        ON e.run_id = r.run_id AND e.candidate_id = r.candidate_id
                    WHERE r.run_id = %s
                    ORDER BY r.rank_position ASC
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()

        for row in rows:
            row["explanation"] = self._normalize_explanation(row.get("explanation"))
        return list(rows)

    def list_results_by_vacancy(
        self,
        vacancy_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM match_results
                    WHERE vacancy_id = %s
                    """,
                    (vacancy_id,),
                )
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

                cur.execute(
                    """
                    SELECT
                        r.run_id,
                        r.candidate_id,
                        r.vacancy_id,
                        r.score,
                        r.rank_position,
                        r.computed_at,
                        e.explanation
                    FROM match_results r
                    LEFT JOIN match_explanations e
                        ON e.run_id = r.run_id AND e.candidate_id = r.candidate_id
                    WHERE r.vacancy_id = %s
                    ORDER BY r.score DESC, r.computed_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (vacancy_id, limit, offset),
                )
                rows = cur.fetchall()

        for row in rows:
            row["explanation"] = self._normalize_explanation(row.get("explanation"))
        return list(rows), total

    def list_results_by_candidate(
        self,
        candidate_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM match_results
                    WHERE candidate_id = %s
                    """,
                    (candidate_id,),
                )
                total_row = cur.fetchone()
                total = int(total_row["total"]) if total_row else 0

                cur.execute(
                    """
                    SELECT
                        r.run_id,
                        r.candidate_id,
                        r.vacancy_id,
                        r.score,
                        r.rank_position,
                        r.computed_at,
                        e.explanation
                    FROM match_results r
                    LEFT JOIN match_explanations e
                        ON e.run_id = r.run_id AND e.candidate_id = r.candidate_id
                    WHERE r.candidate_id = %s
                    ORDER BY r.score DESC, r.computed_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    (candidate_id, limit, offset),
                )
                rows = cur.fetchall()

        for row in rows:
            row["explanation"] = self._normalize_explanation(row.get("explanation"))
        return list(rows), total

    def list_candidate_ids(self, limit: int) -> list[str]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT candidate_id
                    FROM candidates
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [str(row["candidate_id"]) for row in rows]

    def list_vacancy_ids(self, limit: int) -> list[str]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT vacancy_id
                    FROM vacancies
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [str(row["vacancy_id"]) for row in rows]


repository: MatchingRepository | None = None


def get_repository() -> MatchingRepository:
    global repository
    if repository is None:
        repository = MatchingRepository()
    return repository