-- upgrade

CREATE TABLE IF NOT EXISTS author_commit_counts (
    author_login String NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
ENGINE = SummingMergeTree(total)
ORDER BY (repo, author_login)
PRIMARY KEY (repo, author_login)

CREATE MATERIALIZED VIEW IF NOT EXISTS author_commit_counts_mv TO author_commit_counts (
    author_login String NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
AS SELECT repo, author_login, count() AS total FROM commits GROUP BY repo, author_login

CREATE TABLE IF NOT EXISTS commits_per_day (
    day Date NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
ENGINE = SummingMergeTree(total)
ORDER BY (repo, day)
PRIMARY KEY (repo, day)

CREATE MATERIALIZED VIEW IF NOT EXISTS commits_per_day_mv TO commits_per_day (
    day Date NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
AS SELECT repo, toDate(committed_at) AS day, count() AS total FROM commits GROUP BY repo, day

CREATE TABLE IF NOT EXISTS commits_per_month (
    month Date NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
ENGINE = SummingMergeTree(total)
ORDER BY (repo, month)
PRIMARY KEY (repo, month)

CREATE MATERIALIZED VIEW IF NOT EXISTS commits_per_month_mv TO commits_per_month (
    month Date NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
AS SELECT repo, toStartOfMonth(committed_at) AS month, count() AS total FROM commits GROUP BY repo, month

CREATE TABLE IF NOT EXISTS hourly_activity (
    hour Int32 NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
ENGINE = SummingMergeTree(total)
ORDER BY (repo, hour)
PRIMARY KEY (repo, hour)

CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_activity_mv TO hourly_activity (
    hour Int32 NOT NULL,
    repo String NOT NULL,
    total Int64 NOT NULL
)
AS SELECT repo, toHour(committed_at) AS hour, count() AS total FROM commits GROUP BY repo, hour

-- rollback

DROP TABLE author_commit_counts

DROP VIEW author_commit_counts_mv

DROP TABLE commits_per_day

DROP VIEW commits_per_day_mv

DROP TABLE commits_per_month

DROP VIEW commits_per_month_mv

DROP TABLE hourly_activity

DROP VIEW hourly_activity_mv
