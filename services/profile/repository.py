from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from http import HTTPStatus
from typing import Any, Iterator
from uuid import uuid4

from libs import make_http_exception
from libs.sqlalchemy_db import SQLAlchemyConnection, create_postgres_engine


class ProfileRepository:
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
                    CREATE TABLE IF NOT EXISTS candidates (
                        candidate_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        external_id TEXT,
                        full_name TEXT,
                        email TEXT,
                        phone TEXT,
                        location TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_candidates_source_external_id
                    ON candidates (source, external_id)
                    WHERE external_id IS NOT NULL
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS candidate_profiles (
                        candidate_id TEXT PRIMARY KEY REFERENCES candidates(candidate_id) ON DELETE CASCADE,
                        profile JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS resumes (
                        resume_id TEXT PRIMARY KEY,
                        candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
                        source TEXT NOT NULL,
                        external_id TEXT,
                        filename TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        size_bytes BIGINT NOT NULL,
                        storage_key TEXT NOT NULL,
                        parsing_status TEXT NOT NULL,
                        uploaded_by_actor_id TEXT,
                        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_resumes_candidate_id_uploaded_at
                    ON resumes (candidate_id, uploaded_at DESC)
                    """
                )
            conn.commit()

    def get_or_create_candidate(self, source: str, external_id: str | None) -> str:
        with self._connection() as conn:
            with conn.cursor() as cur:
                if external_id:
                    cur.execute(
                        """
                        SELECT candidate_id
                        FROM candidates
                        WHERE source = %s AND external_id = %s
                        LIMIT 1
                        """,
                        (source, external_id),
                    )
                    existing = cur.fetchone()
                    if existing:
                        return str(existing["candidate_id"])

                candidate_id = uuid4().hex
                cur.execute(
                    """
                    INSERT INTO candidates (candidate_id, source, external_id)
                    VALUES (%s, %s, %s)
                    """,
                    (candidate_id, source, external_id),
                )
                cur.execute(
                    """
                    INSERT INTO candidate_profiles (candidate_id, profile)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (candidate_id) DO NOTHING
                    """,
                    (candidate_id, json.dumps({})),
                )
            conn.commit()
            return candidate_id

    def save_resume_metadata(
        self,
        resume_id: str,
        candidate_id: str,
        source: str,
        external_id: str | None,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
        parsing_status: str,
        uploaded_by_actor_id: str,
    ) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO resumes (
                        resume_id,
                        candidate_id,
                        source,
                        external_id,
                        filename,
                        content_type,
                        size_bytes,
                        storage_key,
                        parsing_status,
                        uploaded_by_actor_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        resume_id,
                        candidate_id,
                        source,
                        external_id,
                        filename,
                        content_type,
                        size_bytes,
                        storage_key,
                        parsing_status,
                        uploaded_by_actor_id,
                    ),
                )
            conn.commit()

    @staticmethod
    def _normalize_profile_value(profile_value: Any) -> dict[str, Any]:
        if profile_value is None:
            return {}
        if isinstance(profile_value, dict):
            return profile_value
        if isinstance(profile_value, str):
            try:
                parsed = json.loads(profile_value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.candidate_id,
                        c.source,
                        c.external_id,
                        c.full_name,
                        c.email,
                        c.phone,
                        c.location,
                        c.created_at,
                        c.updated_at,
                        cp.profile,
                        cp.updated_at AS profile_updated_at
                    FROM candidates c
                    LEFT JOIN candidate_profiles cp ON cp.candidate_id = c.candidate_id
                    WHERE c.candidate_id = %s
                    LIMIT 1
                    """,
                    (candidate_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None

        row["profile"] = self._normalize_profile_value(row.get("profile"))
        return row

    def list_candidate_resumes(self, candidate_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        resume_id,
                        candidate_id,
                        source,
                        external_id,
                        filename,
                        content_type,
                        size_bytes,
                        storage_key,
                        parsing_status,
                        uploaded_by_actor_id,
                        uploaded_at
                    FROM resumes
                    WHERE candidate_id = %s
                    ORDER BY uploaded_at DESC
                    """,
                    (candidate_id,),
                )
                rows = cur.fetchall()

        return list(rows)

    def update_candidate(
        self,
        candidate_id: str,
        full_name: str | None,
        email: str | None,
        phone: str | None,
        location: str | None,
        profile_patch: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT candidate_id, full_name, email, phone, location
                    FROM candidates
                    WHERE candidate_id = %s
                    LIMIT 1
                    """,
                    (candidate_id,),
                )
                existing_candidate = cur.fetchone()
                if not existing_candidate:
                    return None

                next_full_name = full_name if full_name is not None else existing_candidate.get("full_name")
                next_email = email if email is not None else existing_candidate.get("email")
                next_phone = phone if phone is not None else existing_candidate.get("phone")
                next_location = location if location is not None else existing_candidate.get("location")

                cur.execute(
                    """
                    UPDATE candidates
                    SET
                        full_name = %s,
                        email = %s,
                        phone = %s,
                        location = %s,
                        updated_at = NOW()
                    WHERE candidate_id = %s
                    """,
                    (next_full_name, next_email, next_phone, next_location, candidate_id),
                )

                if profile_patch is not None:
                    cur.execute(
                        """
                        SELECT profile
                        FROM candidate_profiles
                        WHERE candidate_id = %s
                        LIMIT 1
                        """,
                        (candidate_id,),
                    )
                    current_profile_row = cur.fetchone()
                    current_profile = self._normalize_profile_value(
                        current_profile_row["profile"] if current_profile_row else {}
                    )
                    merged_profile = {**current_profile, **profile_patch}

                    cur.execute(
                        """
                        INSERT INTO candidate_profiles (candidate_id, profile, updated_at)
                        VALUES (%s, %s::jsonb, NOW())
                        ON CONFLICT (candidate_id)
                        DO UPDATE SET profile = EXCLUDED.profile, updated_at = NOW()
                        """,
                        (candidate_id, json.dumps(merged_profile)),
                    )

            conn.commit()

        return self.get_candidate(candidate_id)

    def bulk_get_candidates(self, candidate_ids: list[str]) -> list[dict[str, Any]]:
        if not candidate_ids:
            return []

        placeholders = ", ".join(["%s"] * len(candidate_ids))
        query = f"""
            SELECT
                c.candidate_id,
                c.source,
                c.external_id,
                c.full_name,
                c.email,
                c.phone,
                c.location,
                c.created_at,
                c.updated_at,
                cp.profile,
                cp.updated_at AS profile_updated_at
            FROM candidates c
            LEFT JOIN candidate_profiles cp ON cp.candidate_id = c.candidate_id
            WHERE c.candidate_id IN ({placeholders})
        """

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(candidate_ids))
                rows = cur.fetchall()

        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            row["profile"] = self._normalize_profile_value(row.get("profile"))
            normalized_rows.append(row)
        return normalized_rows


repository: ProfileRepository | None = None


def get_repository() -> ProfileRepository:
    global repository
    if repository is None:
        repository = ProfileRepository()
    return repository