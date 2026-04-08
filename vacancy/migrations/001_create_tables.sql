-- Vacancy-сервис: таблицы vacancies, vacancy_requirements.
-- Миграция идемпотентна (IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS vacancies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    department VARCHAR(100),
    location VARCHAR(255) NOT NULL,
    grade TEXT[] NOT NULL DEFAULT '{}',
    salary_min INTEGER,
    salary_max INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_vacancies_status ON vacancies (status);
CREATE INDEX IF NOT EXISTS ix_vacancies_department ON vacancies (department);
CREATE INDEX IF NOT EXISTS ix_vacancies_location ON vacancies (location);
CREATE INDEX IF NOT EXISTS ix_vacancies_created_at ON vacancies (created_at DESC);

CREATE TABLE IF NOT EXISTS vacancy_requirements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vacancy_id UUID NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    skill VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    min_experience_years NUMERIC(4, 1)
);

CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_vacancy_id ON vacancy_requirements (vacancy_id);
CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_skill ON vacancy_requirements (skill);
