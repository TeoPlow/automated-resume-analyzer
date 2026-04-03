Migration usage (Alembic alternative)

1. Apply schema migrations:
python scripts/apply_migrations.py

2. Seed demo data for cross-service business flows:
python scripts/seed_demo_data.py

Notes:
- Scripts read PostgreSQL settings from environment variables.
- Migrations are idempotent and tracked in schema_migrations.
