-- upgrade

CREATE TABLE IF NOT EXISTS excluded_repos (
    full_name String
)
ENGINE = ReplacingMergeTree
ORDER BY full_name
PRIMARY KEY full_name COMMENT 'Repos excluded from sync';

-- rollback

DROP TABLE IF EXISTS excluded_repos
