CREATE TABLE games (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    created_at_utc  TEXT NOT NULL,
    updated_at_utc  TEXT NOT NULL
);

CREATE TABLE jobs (
    id                     INTEGER PRIMARY KEY,
    game_id                INTEGER NOT NULL REFERENCES games(id),
    name                   TEXT NOT NULL,
    runner_type            TEXT NOT NULL,
    runner_config_version  INTEGER NOT NULL DEFAULT 1,
    runner_config_json     TEXT NOT NULL,
    enabled                INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    queue_order             INTEGER NOT NULL,
    timezone_id             TEXT NOT NULL,
    reset_minute            INTEGER NOT NULL CHECK(reset_minute BETWEEN 0 AND 1439),
    created_at_utc          TEXT NOT NULL,
    updated_at_utc          TEXT NOT NULL
);

CREATE TABLE runs (
    id                    TEXT PRIMARY KEY,
    job_id                INTEGER NOT NULL REFERENCES jobs(id),
    trigger_type          TEXT NOT NULL,
    state                 TEXT NOT NULL,
    started_at_utc        TEXT,
    finished_at_utc       TEXT,
    exit_code             INTEGER,
    exit_status           TEXT,
    error_kind            TEXT,
    error_summary         TEXT,
    stdout_path           TEXT,
    stderr_path           TEXT,
    launch_snapshot_json  TEXT NOT NULL,
    created_at_utc        TEXT NOT NULL
);

CREATE TABLE daily_completions (
    job_id             INTEGER NOT NULL REFERENCES jobs(id),
    period_start_utc   TEXT NOT NULL,
    completed_at_utc   TEXT NOT NULL,
    source             TEXT NOT NULL,
    run_id             TEXT REFERENCES runs(id),
    PRIMARY KEY(job_id, period_start_utc)
);

CREATE INDEX idx_jobs_queue_order ON jobs(enabled, queue_order);
CREATE INDEX idx_runs_job_started ON runs(job_id, started_at_utc DESC);
CREATE INDEX idx_daily_completions_job_period
    ON daily_completions(job_id, period_start_utc);
