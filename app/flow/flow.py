from datetime import datetime, timezone
import logging

from prefect import flow, get_run_logger, task
from prefect.exceptions import MissingContextError

from app.flow.tasks import (
    RepoRecord,
    get_existing_commit_shas,
    repo_indexing,
    fetch_commits,
    get_sync_state,
    insert_commits,
    transform_commit,
    update_sync_state,
)
from app.services.client import get_clickhouse_client


@task
def process_repo(repo: RepoRecord):
    try:
        log = get_run_logger()
    except MissingContextError:
        log = logging.getLogger("vigil")
    last_synced_at, last_synced_sha = get_sync_state(repo.full_name)

    try:
        existing_shas = get_existing_commit_shas(repo.full_name, last_synced_at)
        raw_commits = fetch_commits(repo.full_name, last_synced_at, last_synced_sha)

        if existing_shas:
            raw_commits = [raw_commit for raw_commit in raw_commits if raw_commit["sha"] not in existing_shas]

        if not raw_commits:
            update_sync_state(repo.full_name, last_synced_at, last_synced_sha, "success")
            log.info(f"{repo.full_name}: no new commits")
            return 0

        commit_records = [transform_commit(raw_commit, repo.full_name) for raw_commit in raw_commits]
        inserted = insert_commits(commit_records)

        newest_commit = max(raw_commits, key=lambda item: item["committed_at"])
        update_sync_state(repo.full_name, newest_commit["committed_at"], newest_commit["sha"], "success")
        log.info(f"{repo.full_name}: synced {inserted} commits")
        return inserted

    except Exception:
        update_sync_state(
            repo.full_name,
            last_synced_at or datetime.now(timezone.utc),
            last_synced_sha or "",
            "failure",
        )
        raise


@task
def get_excluded_repos() -> set[str]:
    client = get_clickhouse_client()
    try:
        result = client.query("SELECT full_name FROM excluded_repos FINAL")
        return {row[0] for row in result.result_rows}
    finally:
        client.close()


@flow(log_prints=True)
def vigil_sync():
    repos = repo_indexing()
    excluded = get_excluded_repos()
    filtered = [r for r in repos if r.full_name not in excluded]
    if excluded:
        log = logging.getLogger("vigil")
        log.info(f"Excluded {len(excluded)} repos from sync, processing {len(filtered)} repos")
    process_repo.map(filtered).result()
