CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS match_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vacancy_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_candidates INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_match_runs_vacancy_id ON match_runs (vacancy_id);
CREATE INDEX IF NOT EXISTS ix_match_runs_status ON match_runs (status);
CREATE INDEX IF NOT EXISTS ix_match_runs_started_at ON match_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS match_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES match_runs(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL,
    vacancy_id UUID NOT NULL,
    final_score NUMERIC(5, 2) NOT NULL,
    skill_score NUMERIC(5, 2) NOT NULL,
    experience_score NUMERIC(5, 2) NOT NULL,
    grade_score NUMERIC(5, 2) NOT NULL,
    location_score NUMERIC(5, 2) NOT NULL,
    salary_score NUMERIC(5, 2) NOT NULL,
    rank INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_match_results_run_id ON match_results (run_id);
CREATE INDEX IF NOT EXISTS ix_match_results_vacancy_id ON match_results (vacancy_id, final_score DESC);
CREATE INDEX IF NOT EXISTS ix_match_results_candidate_id ON match_results (candidate_id, final_score DESC);
CREATE INDEX IF NOT EXISTS ix_match_results_rank ON match_results (run_id, rank ASC);

CREATE TABLE IF NOT EXISTS match_explanations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    result_id UUID NOT NULL REFERENCES match_results(id) ON DELETE CASCADE,
    factor VARCHAR(50) NOT NULL,
    detail TEXT NOT NULL,
    score NUMERIC(5, 2) NOT NULL,
    weight NUMERIC(3, 2) NOT NULL,
    impact NUMERIC(5, 2) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_match_explanations_result_id ON match_explanations (result_id);
