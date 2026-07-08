from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from github import GithubException, RateLimitExceededException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.client import get_clickhouse_client, get_repo_handle, github_session
from app.services.commits import extract_commit_data
from app.flow.tasks import RepoRecord, repo_indexing


logger = logging.getLogger("vigil.rebuild_commits")

COMMIT_COLUMNS = [
    "repo",
    "sha",
    "author_login",
    "author_name",
    "author_email",
    "message",
    "is_merge",
    "committed_at",
]

DERIVED_TABLES = [
    "author_commit_counts",
    "commits_per_day",
    "commits_per_month",
    "hourly_activity",
    "author_commit_days",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely rebuild commits and derived ClickHouse tables from GitHub.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel GitHub fetch workers.")
    parser.add_argument("--batch-size", type=int, default=1000, help="ClickHouse insert batch size.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, but do not modify ClickHouse.")
    parser.add_argument("--confirm", action="store_true", help="Required to perform destructive rebuild steps.")
    parser.add_argument("--drop-backup", action="store_true", help="Drop the backup table after a successful rebuild.")
    return parser.parse_args(argv)


def _should_delegate_to_container() -> bool:
    return os.getenv("VIGIL_IN_CONTAINER") != "1" and os.getenv("VIGIL_SKIP_DOCKER_DELEGATION") != "1"


def _delegate_to_container(argv: list[str]) -> int:
    if shutil.which("docker") is None:
        raise SystemExit("docker is required to run this script from the host; start the app container and retry")

    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "app",
        "env",
        "VIGIL_IN_CONTAINER=1",
        "uv",
        "run",
        "python",
        "scripts/rebuild_clickhouse_commits.py",
        *argv,
    ]
    result = subprocess.run(command, check=False)
    return result.returncode


def _chunked(items: list[list], size: int) -> list[list[list]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _create_backup_table(client, backup_table: str) -> None:
    client.command(
        f"CREATE TABLE {backup_table} AS commits ENGINE = MergeTree() ORDER BY (repo, committed_at) PRIMARY KEY repo"
    )
    client.command(f"INSERT INTO {backup_table} SELECT * FROM commits")


def _drop_tables(client, tables: list[str]) -> None:
    for table in tables:
        client.command(f"TRUNCATE TABLE {table}")


def _restore_from_backup(client, backup_table: str) -> None:
    _drop_tables(client, ["commits", *DERIVED_TABLES])
    client.command(f"INSERT INTO commits SELECT * FROM {backup_table}")


def _fetch_repo_commits(repo: RepoRecord) -> tuple[str, list[list], int]:
    with github_session() as gh:
        repo_handle = get_repo_handle(gh, repo.full_name)

        for attempt in range(3):
            try:
                fetched = list(repo_handle.get_commits())
                break
            except GithubException as exc:
                status = getattr(exc, "status", None)
                if status == 409:
                    logger.info("%s: repository is empty, skipping", repo.full_name)
                    return repo.full_name, [], 0
                raise
            except RateLimitExceededException:
                reset_time = gh.get_rate_limit().core.reset
                sleep_for = max((reset_time - datetime.now(timezone.utc)).total_seconds(), 60.0)
                logger.warning(
                    "Rate limit hit for %s, sleeping %.0fs before retry %s/3",
                    repo.full_name,
                    sleep_for,
                    attempt + 2,
                )
                time.sleep(sleep_for)
                continue
        else:
            raise RuntimeError(f"Unable to fetch commits for {repo.full_name} after retries")

        rows: list[list] = []
        for commit in fetched:
            data = extract_commit_data(commit)
            data["author_login"] = settings.canonical_author_login(data["author_login"])
            rows.append(
                [
                    repo.full_name,
                    data["sha"],
                    data["author_login"],
                    data["author_name"],
                    data["author_email"],
                    data["message"],
                    data["is_merge"],
                    data["committed_at"],
                ]
            )

        return repo.full_name, rows, len(fetched)


def _fetch_all_rows(repos: list[RepoRecord], workers: int) -> list[list]:
    fetched_rows: list[list] = []
    total_fetched = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_repo_commits, repo): repo for repo in repos}
        for future in as_completed(futures):
            repo_name, rows, fetched_count = future.result()
            logger.info("%s: fetched %d commits, keeping %d", repo_name, fetched_count, len(rows))
            total_fetched += fetched_count
            fetched_rows.extend(rows)

    logger.info("Fetched %d commits across %d repos", total_fetched, len(repos))
    return fetched_rows


def _insert_rows(client, rows: list[list], batch_size: int) -> int:
    inserted = 0
    for batch in _chunked(rows, batch_size):
        client.insert("commits", data=batch, column_names=COMMIT_COLUMNS)
        inserted += len(batch)
    return inserted


def _run_local(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)

    repos = repo_indexing.fn()
    if not repos:
        logger.info("No repos found; nothing to rebuild")
        return 0

    logger.info("Preparing full rebuild for %d repos", len(repos))
    rows = _fetch_all_rows(repos, args.workers)
    logger.info("Prepared %d commit rows", len(rows))

    if args.dry_run:
        print(f"dry-run repos={len(repos)} rows={len(rows)}")
        return 0

    if not args.confirm:
        raise SystemExit("refusing to modify ClickHouse without --confirm")

    backup_table = f"commits_backup_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    client = get_clickhouse_client()
    try:
        logger.info("Creating backup table %s", backup_table)
        _create_backup_table(client, backup_table)

        logger.info("Truncating source and derived tables")
        _drop_tables(client, ["commits", *DERIVED_TABLES])

        logger.info("Inserting %d commit rows", len(rows))
        inserted = _insert_rows(client, rows, args.batch_size)
        logger.info("Inserted %d commit rows", inserted)

        counts = client.query("SELECT count() FROM commits").result_rows[0][0]
        logger.info("Rebuild complete, commits now has %s rows", counts)

        if args.drop_backup:
            client.command(f"DROP TABLE {backup_table}")
            logger.info("Dropped backup table %s", backup_table)

        print(f"rebuild complete backup={backup_table} inserted={inserted}")
        return 0
    except Exception:
        logger.exception("Rebuild failed; restoring from backup %s", backup_table)
        try:
            _restore_from_backup(client, backup_table)
            logger.info("Restore from backup %s completed", backup_table)
        finally:
            if args.drop_backup:
                logger.warning("Keeping backup table %s because the rebuild failed", backup_table)
        raise
    finally:
        client.close()


def main() -> None:
    if _should_delegate_to_container():
        raise SystemExit(_delegate_to_container(sys.argv[1:]))

    raise SystemExit(_run_local(sys.argv[1:]))


if __name__ == "__main__":
    main()
