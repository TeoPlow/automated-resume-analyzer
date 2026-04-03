from __future__ import annotations

import logging
import os
from pathlib import Path

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


def _discover_migrations(migrations_dir: Path) -> list[Path]:
    return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())


def apply_migrations() -> None:
    engine = _build_engine()

    project_root = Path(__file__).resolve().parents[1]
    migrations_dir = project_root / "migrations"
    migration_files = _discover_migrations(migrations_dir)

    if not migration_files:
        logger.info("No migrations found")
        return

    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        applied_rows = conn.exec_driver_sql("SELECT version FROM schema_migrations").all()
        applied_versions = {str(row[0]) for row in applied_rows}

        for migration_path in migration_files:
            version = migration_path.name
            if version in applied_versions:
                logger.info("Skip %s: already applied", version)
                continue

            sql_text = migration_path.read_text(encoding="utf-8")
            logger.info("Applying %s...", version)
            conn.exec_driver_sql(sql_text)
            conn.exec_driver_sql(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )

        conn.commit()

    logger.info("Migrations applied successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    apply_migrations()
