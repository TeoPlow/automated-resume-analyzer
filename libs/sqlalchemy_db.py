from __future__ import annotations

import os
from typing import Any

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Connection, CursorResult, Engine


class SQLAlchemyCursor:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._result: CursorResult[Any] | None = None

    def __enter__(self) -> "SQLAlchemyCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        if params is None:
            self._result = self._connection.exec_driver_sql(sql)
            return
        self._result = self._connection.exec_driver_sql(sql, params)

    def fetchone(self) -> dict[str, Any] | None:
        if self._result is None:
            return None
        row = self._result.mappings().first()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, Any]]:
        if self._result is None:
            return []
        return [dict(row) for row in self._result.mappings().all()]


class SQLAlchemyConnection:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def cursor(self) -> SQLAlchemyCursor:
        return SQLAlchemyCursor(self._connection)

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


def create_postgres_engine(default_host: str) -> Engine:
    host = os.getenv("POSTGRES_HOST", default_host)
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