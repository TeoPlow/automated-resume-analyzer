-- Profile-сервис: таблицы candidates, resumes, candidate_profiles.
-- Миграция идемпотентна (IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_candidates_email ON candidates (email);
CREATE INDEX IF NOT EXISTS ix_candidates_phone ON candidates (phone);
CREATE INDEX IF NOT EXISTS ix_candidates_created_at ON candidates (created_at DESC);

CREATE TABLE IF NOT EXISTS resumes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
    file_key VARCHAR(512) NOT NULL,
    source VARCHAR(50) NOT NULL,
    external_id VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    raw_text TEXT,
    parsed_data JSONB,
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_resumes_candidate_id ON resumes (candidate_id);
CREATE INDEX IF NOT EXISTS ix_resumes_status ON resumes (status);
CREATE INDEX IF NOT EXISTS ix_resumes_created_at ON resumes (created_at DESC);

CREATE TABLE IF NOT EXISTS candidate_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    skills TEXT[] NOT NULL DEFAULT '{}',
    grade VARCHAR(20),
    location VARCHAR(255),
    experience_years NUMERIC(4, 1),
    salary_expectation INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_candidate_profile UNIQUE (candidate_id)
);

CREATE INDEX IF NOT EXISTS ix_candidate_profiles_grade ON candidate_profiles (grade);
CREATE INDEX IF NOT EXISTS ix_candidate_profiles_location ON candidate_profiles (location);
CREATE INDEX IF NOT EXISTS ix_candidate_profiles_skills_gin ON candidate_profiles USING gin (skills);
