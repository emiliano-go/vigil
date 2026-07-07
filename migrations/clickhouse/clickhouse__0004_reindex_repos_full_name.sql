-- upgrade

DROP TABLE IF EXISTS repos_v2

CREATE TABLE IF NOT EXISTS repos_v2 (
    full_name String NOT NULL,
    name String NOT NULL,
    owner String NOT NULL,
    is_org Bool NOT NULL,
    private Bool NOT NULL,
    default_branch String NOT NULL
)
ENGINE = ReplacingMergeTree()
ORDER BY (full_name)
PRIMARY KEY full_name

INSERT INTO repos_v2 (full_name, name, owner, is_org, private, default_branch)
SELECT concat(owner, '/', name) AS full_name, name, owner, is_org, false AS private, default_branch
FROM repos

DROP TABLE repos

RENAME TABLE repos_v2 TO repos

-- rollback

DROP TABLE IF EXISTS repos_legacy

CREATE TABLE IF NOT EXISTS repos_legacy (
    name String NOT NULL,
    owner String NOT NULL,
    is_org Bool NOT NULL,
    default_branch String NOT NULL
)
ENGINE = ReplacingMergeTree()
ORDER BY (name)
PRIMARY KEY name

INSERT INTO repos_legacy (name, owner, is_org, default_branch)
SELECT name, owner, is_org, default_branch
FROM repos

DROP TABLE repos

RENAME TABLE repos_legacy TO repos
