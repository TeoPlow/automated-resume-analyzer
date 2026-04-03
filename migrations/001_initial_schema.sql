-- Initial schema for automated-resume-analyzer MVP.
-- This migration is idempotent and can be applied repeatedly.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_candidates_source_external_id
ON candidates (source, external_id)
WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS candidate_profiles (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
);

CREATE INDEX IF NOT EXISTS ix_resumes_candidate_id_uploaded_at
ON resumes (candidate_id, uploaded_at DESC);

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
);

CREATE TABLE IF NOT EXISTS vacancy_requirements (
    requirement_id BIGSERIAL PRIMARY KEY,
    vacancy_id TEXT NOT NULL REFERENCES vacancies(vacancy_id) ON DELETE CASCADE,
    requirement_type TEXT NOT NULL DEFAULT 'skill',
    raw_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    weight NUMERIC(5, 2) NOT NULL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_vacancy_id
ON vacancy_requirements (vacancy_id);

CREATE INDEX IF NOT EXISTS ix_vacancy_requirements_normalized
ON vacancy_requirements (normalized_value);

CREATE INDEX IF NOT EXISTS ix_vacancies_status_updated_at
ON vacancies (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS match_runs (
    run_id TEXT PRIMARY KEY,
    vacancy_id TEXT NOT NULL,
    initiated_by_actor_id TEXT,
    top_k INTEGER NOT NULL,
    force_recompute BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_match_runs_vacancy_created_at
ON match_runs (vacancy_id, created_at DESC);

CREATE TABLE IF NOT EXISTS match_results (
    match_result_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES match_runs(run_id) ON DELETE CASCADE,
    vacancy_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    score NUMERIC(5, 2) NOT NULL,
    rank_position INTEGER NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_match_results_run_rank
ON match_results (run_id, rank_position ASC);

CREATE INDEX IF NOT EXISTS ix_match_results_vacancy_score
ON match_results (vacancy_id, score DESC);

CREATE INDEX IF NOT EXISTS ix_match_results_candidate_score
ON match_results (candidate_id, score DESC);

CREATE TABLE IF NOT EXISTS match_explanations (
    explanation_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES match_runs(run_id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL,
    explanation JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_match_explanations_run_candidate
ON match_explanations (run_id, candidate_id);

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
