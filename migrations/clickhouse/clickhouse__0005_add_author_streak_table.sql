-- upgrade

CREATE MATERIALIZED VIEW IF NOT EXISTS commits_per_day_mv TO commits_per_day (
    repo String,
    day Date,
    total Int64
)
AS SELECT repo, toDate(committed_at) AS day, count() AS total FROM commits GROUP BY repo, day COMMENT 'Materialized view for commits per day';

CREATE MATERIALIZED VIEW IF NOT EXISTS commits_per_month_mv TO commits_per_month (
    repo String,
    month Date,
    total Int64
)
AS SELECT repo, toStartOfMonth(committed_at) AS month, count() AS total FROM commits GROUP BY repo, month COMMENT 'Materialized view for commits per month';

CREATE MATERIALIZED VIEW IF NOT EXISTS author_commit_counts_mv TO author_commit_counts (
    repo String,
    author_login String,
    total Int64
)
AS SELECT repo, author_login, count() AS total FROM commits GROUP BY repo, author_login COMMENT 'Materialized view for author commit counts';

CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_activity_mv TO hourly_activity (
    repo String,
    hour Int32,
    total Int64
)
AS SELECT repo, toHour(committed_at) AS hour, count() AS total FROM commits GROUP BY repo, hour COMMENT 'Materialized view for hourly activity';

CREATE TABLE IF NOT EXISTS author_commit_days (
    author_login String,
    day Date,
    total Int64
)
ENGINE = SummingMergeTree(total)
ORDER BY (author_login, day)
PRIMARY KEY (author_login, day) COMMENT 'Daily commit counts per author';

CREATE MATERIALIZED VIEW IF NOT EXISTS author_commit_days_mv TO author_commit_days (
    author_login String,
    day Date,
    total Int64
)
AS SELECT author_login, toDate(committed_at) AS day, count() AS total FROM commits GROUP BY author_login, day COMMENT 'Materialized view for daily author commit counts';

ALTER TABLE commits ADD COLUMN is_merge Bool DEFAULT false

ALTER TABLE repos ADD COLUMN full_name String

ALTER TABLE repos ADD COLUMN private Bool

-- rollback

ALTER TABLE repos DROP COLUMN private

ALTER TABLE repos DROP COLUMN full_name

ALTER TABLE commits DROP COLUMN is_merge

DROP VIEW IF EXISTS author_commit_days_mv

DROP TABLE author_commit_days

DROP VIEW IF EXISTS hourly_activity_mv

DROP VIEW IF EXISTS author_commit_counts_mv

DROP VIEW IF EXISTS commits_per_month_mv

DROP VIEW IF EXISTS commits_per_day_mv
