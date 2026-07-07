from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from prefect import get_run_logger, task
from prefect.exceptions import MissingContextError
from github import GithubException, RateLimitExceededException

from app.services.client import get_clickhouse_client, get_repo_handle, github_session
from app.services.commits import extract_commit_data
from app.models.commit import Commit

@dataclass(frozen=True)
class RepoRecord:
    full_name: str
    name: str
    owner: str
    is_org: bool
    private: bool
    default_branch: str


def _get_logger():
    try:
        return get_run_logger()
    except MissingContextError:
        return logging.getLogger("vigil")

@task(retries=3, retry_delay_seconds=[10, 30, 90])
def repo_indexing():
    log = _get_logger()

    with github_session() as gh:
        try:
            github_repos = list(gh.get_user().get_repos())
        except RateLimitExceededException:
            reset_time = gh.get_rate_limit().core.reset
            log.warning(f"Rate limit hit while indexing repos, resets at {reset_time}: letting Prefect retry")
            raise

    repos = [
        RepoRecord(
            full_name=repo.full_name,
            name=repo.name,
            owner=repo.owner.login,
            is_org=getattr(repo.owner, "type", "") == "Organization",
            private=bool(repo.private),
            default_branch=repo.default_branch or "main",
        )
        for repo in github_repos
    ]
    repos.sort(key=lambda item: item.full_name)

    client = get_clickhouse_client()
    columns = ["full_name", "name", "owner", "is_org", "private", "default_branch"]

    try:
        client.command("TRUNCATE TABLE repos")
        rows = [
            (repo.full_name, repo.name, repo.owner, repo.is_org, repo.private, repo.default_branch)
            for repo in repos
        ]
        if rows:
            client.insert("repos", data=rows, column_names=columns)
        log.info(f"Indexed {len(rows)} repos from GitHub")
    finally:
        client.close()

    return repos

@task
def get_sync_state(repo_full_name: str):
    client = get_clickhouse_client()

    try:
        result = client.query(
            "SELECT last_synced_at, last_synced_sha FROM sync_state WHERE repo = %(repo)s",
            parameters={"repo": repo_full_name},
        )

        if result.result_rows:
            last_synced_at, last_synced_sha = result.result_rows[0]
        else:
            last_synced_at, last_synced_sha = None, None

        return (last_synced_at, last_synced_sha)

    finally:
        client.close()

@task(retries=3, retry_delay_seconds=[10, 30, 90])
def fetch_commits(repo_full_name: str, since_datetime: datetime | None):
    log = _get_logger()

    with github_session() as gh:
        try:
            repo_handle = get_repo_handle(gh, repo_full_name)

            if since_datetime is None:
                commits = repo_handle.get_commits()
            else:
                commits = repo_handle.get_commits(since=since_datetime)

            results = []

            try:
                for commit in commits:
                    results.append(extract_commit_data(commit))
            except GithubException as exc:
                if getattr(exc, "status", None) == 409:
                    log.info(f"{repo_full_name} is empty, skipping commit fetch")
                    return []
                raise

            log.info(f"{repo_full_name} -> {len(results)} commits fetched (since={since_datetime})")
            return results
        
        except RateLimitExceededException:
            reset_time = gh.get_rate_limit().core.reset
            log.warning(f"Rate limit hit for {repo_full_name}, resets at {reset_time}: letting Prefect retry")
            raise


@task
def transform_commit(raw_commit, repo_full_name):
    return Commit.Schema(
        repo=repo_full_name,
        sha=raw_commit["sha"],
        author_name=raw_commit["author_name"],
        author_email=raw_commit["author_email"],
        author_login=raw_commit["author_login"],
        committed_at=raw_commit["committed_at"],
        message=raw_commit["message"],
        is_merge=raw_commit["is_merge"],
    )

@task(retries=2, retry_delay_seconds=5)
def insert_commits(commit_records):
    log = _get_logger()

    if not commit_records:
        return 0

    client = get_clickhouse_client()

    columns = [
        "repo",
        "sha",
        "author_login",
        "author_name",
        "author_email",
        "message",
        "is_merge",
        "committed_at",
    ]

    def _value(record, column):
        if isinstance(record, dict):
            return record[column]
        return getattr(record, column)

    try:
        rows = [tuple(_value(record, column) for column in columns) for record in commit_records]
        client.insert("commits", data=rows, column_names=columns)
        log.info(f"{len(commit_records)} commits have been saved to clickhouse")

    finally:
        client.close()
    
    return len(commit_records)


@task(retries=2, retry_delay_seconds=5)
def update_sync_state(repo_full_name, last_synced_at, last_synced_sha, status):
    log = _get_logger()

    client = get_clickhouse_client()

    effective_last_synced_at = last_synced_at or datetime.now(timezone.utc)
    effective_last_synced_sha = last_synced_sha or ""

    try:
        client.insert(
            "sync_state",
            data=[[repo_full_name, effective_last_synced_at, effective_last_synced_sha, status, datetime.now(timezone.utc)]],
            column_names=["repo", "last_synced_at", "last_synced_sha", "last_run_status", "last_run_at"],
        )
        log.info(f"sync_state updated for {repo_full_name}: {status}")

    finally:
        client.close()
