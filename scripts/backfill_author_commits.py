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
from app.flow.tasks import RepoRecord
from app.services.client import get_clickhouse_client, get_repo_handle, github_session
from app.services.commits import extract_commit_data
from app.services.github_contributions import get_viewer_login


logger = logging.getLogger("vigil.backfill_author_commits")

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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill commits for a specific author from GitHub into ClickHouse.")
    parser.add_argument("--author-login", default=None, help="Canonical GitHub login to backfill. Defaults to the viewer login.")
    parser.add_argument("--since", default="2022-01-01", help="Backfill commits since this date (YYYY-MM-DD or ISO datetime).")
    parser.add_argument("--workers", type=int, default=4, help="Parallel GitHub fetch workers.")
    parser.add_argument("--batch-size", type=int, default=1000, help="ClickHouse insert batch size.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, but do not insert.")
    parser.add_argument("--refresh-existing", action="store_true", help="Allow re-inserting rows even if they already exist in ClickHouse.")
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
        "scripts/backfill_author_commits.py",
        *argv,
    ]
    result = subprocess.run(command, check=False)
    return result.returncode


def _chunked(items: list[list], size: int) -> list[list[list]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _parse_since(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _repo_records() -> list[RepoRecord]:
    with github_session() as gh:
        repos = [
            RepoRecord(
                full_name=repo.full_name,
                name=repo.name,
                owner=repo.owner.login,
                is_org=getattr(repo.owner, "type", "") == "Organization",
                private=bool(repo.private),
                default_branch=repo.default_branch or "main",
            )
            for repo in gh.get_user().get_repos()
        ]

    repos.sort(key=lambda item: item.full_name)
    return repos


def _existing_keys(client, since: datetime) -> set[tuple[str, str]]:
    result = client.query(
        "SELECT repo, sha FROM commits WHERE committed_at >= %(since)s",
        parameters={"since": since},
    )
    return {(row[0], row[1]) for row in result.result_rows}


def _resolve_author_logins(author_login: str) -> list[str]:
    aliases = settings.author_login_aliases(author_login)
    return aliases


def _fetch_repo_commits(repo, author_logins: list[str], since: datetime) -> tuple[str, list[list], int]:
    with github_session() as gh:
        repo_handle = get_repo_handle(gh, repo.full_name)

        rows: list[list] = []
        total_fetched = 0
        seen_shas: set[str] = set()

        for author_login in author_logins:
            for attempt in range(3):
                try:
                    fetched = list(repo_handle.get_commits(author=author_login, since=since))
                    break
                except GithubException as exc:
                    if getattr(exc, "status", None) == 409:
                        logger.info("%s: repository is empty, skipping", repo.full_name)
                        return repo.full_name, [], 0
                    raise
                except RateLimitExceededException:
                    reset_time = gh.get_rate_limit().core.reset
                    sleep_for = max((reset_time - datetime.now(timezone.utc)).total_seconds(), 60.0)
                    logger.warning(
                        "Rate limit hit for %s (%s), sleeping %.0fs before retry %s/3",
                        repo.full_name,
                        author_login,
                        sleep_for,
                        attempt + 2,
                    )
                    time.sleep(sleep_for)
            else:
                raise RuntimeError(f"Unable to fetch commits for {repo.full_name} and {author_login} after retries")

            total_fetched += len(fetched)

            for commit in fetched:
                data = extract_commit_data(commit)
                if data["sha"] in seen_shas:
                    continue
                seen_shas.add(data["sha"])
                data["author_login"] = settings.canonical_author_login(data["author_login"] or author_login)
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

        return repo.full_name, rows, total_fetched


def _insert_rows(client, rows: list[list], batch_size: int) -> int:
    inserted = 0
    for batch in _chunked(rows, batch_size):
        client.insert("commits", data=batch, column_names=COMMIT_COLUMNS)
        inserted += len(batch)
    return inserted


def _run_local(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)

    since = _parse_since(args.since)
    author_login = args.author_login or settings.canonical_author_login(get_viewer_login())
    author_logins = _resolve_author_logins(author_login)

    logger.info("Backfilling author commits since %s for %s (%s)", since.isoformat(), author_login, ", ".join(author_logins))

    repos = _repo_records()
    if not repos:
        logger.info("No repos found; nothing to backfill")
        return 0

    client = get_clickhouse_client()
    try:
        existing_keys = _existing_keys(client, since)
    finally:
        client.close()

    logger.info("Found %d existing commit keys in the backfill window", len(existing_keys))

    fetched_rows: list[list] = []
    total_fetched = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_fetch_repo_commits, repo, author_logins, since): repo for repo in repos}
        for future in as_completed(futures):
            repo_name, rows, fetched_count = future.result()
            total_fetched += fetched_count
            logger.info("%s: fetched %d author commits, keeping %d", repo_name, fetched_count, len(rows))
            if args.refresh_existing:
                fetched_rows.extend(rows)
            else:
                for row in rows:
                    if (row[0], row[1]) in existing_keys:
                        continue
                    fetched_rows.append(row)

    logger.info("Prepared %d new commit rows from %d fetched author commits", len(fetched_rows), total_fetched)

    if args.dry_run:
        print(f"dry-run fetched={total_fetched} new_rows={len(fetched_rows)} author={author_login} since={since.date().isoformat()}")
        return 0

    if not fetched_rows:
        logger.info("No new commit rows to insert")
        return 0

    client = get_clickhouse_client()
    try:
        inserted = _insert_rows(client, fetched_rows, args.batch_size)
        logger.info("Inserted %d commit rows", inserted)
        print(f"inserted={inserted} author={author_login}")
    finally:
        client.close()

    return 0


def main() -> None:
    if _should_delegate_to_container():
        raise SystemExit(_delegate_to_container(sys.argv[1:]))

    raise SystemExit(_run_local(sys.argv[1:]))


if __name__ == "__main__":
    main()
