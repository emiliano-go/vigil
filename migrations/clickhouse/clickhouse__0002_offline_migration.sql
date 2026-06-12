-- upgrade

CREATE TABLE IF NOT EXISTS sync_state (
    last_run_at DateTime64(3) NOT NULL,
    last_run_status String NOT NULL,
    last_synced_at DateTime64(3) NOT NULL,
    last_synced_sha String NOT NULL,
    repo NULL NOT NULL REFERENCES repos(name)
)
ENGINE = ReplacingMergeTree()
ORDER BY (repo)
PRIMARY KEY repo

ALTER TABLE sync_state ADD CONSTRAINT sync_state_repo_fkey FOREIGN KEY (repo) REFERENCES repos(name);

-- rollback

DROP TABLE sync_state

ALTER TABLE sync_state DROP CONSTRAINT sync_state_repo_fkey;
