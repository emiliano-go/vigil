from __future__ import annotations

import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from github import RateLimitExceededException


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.flow.tasks import RepoRecord, repo_indexing
from app.services.client import get_clickhouse_client, get_repo_handle, github_session
from app.services.commits import extract_commit_data


logger = logging.getLogger("vigil.populate")

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill the last month of commits into ClickHouse.")
    parser.add_argument("--days", type=int, default=30, help="How many days back to fetch commits.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel GitHub fetch workers.")
    parser.add_argument("--batch-size", type=int, default=1000, help="ClickHouse insert batch size.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, but do not insert.")
    return parser.parse_args()


def _chunked(items: list[list], size: int) -> list[list[list]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _existing_commit_shas(client, since: datetime) -> set[str]:
    result = client.query(
        "SELECT sha FROM commits WHERE committed_at >= %(since)s",
        parameters={"since": since},
    )
    return {row[0] for row in result.result_rows}


def _fetch_repo_commits(repo: RepoRecord, since: datetime, existing_shas: set[str]) -> tuple[str, list[list], int]:
    with github_session() as gh:
        repo_handle = get_repo_handle(gh, repo.full_name)

        for attempt in range(3):
            try:
                fetched = list(repo_handle.get_commits(since=since))
                break
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
        else:
            raise RuntimeError(f"Unable to fetch commits for {repo.full_name} after retries")

        rows: list[list] = []
        for commit in fetched:
            data = extract_commit_data(commit)
            if data["sha"] in existing_shas:
                continue
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


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    logger.info("Backfilling commits since %s", since.isoformat())

    repos = repo_indexing.fn()
    client = get_clickhouse_client()
    try:
        existing_shas = _existing_commit_shas(client, since)
    finally:
        client.close()

    logger.info("Found %d existing shas in the backfill window", len(existing_shas))

    fetched_rows: list[list] = []
    total_fetched = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_fetch_repo_commits, repo, since, existing_shas): repo for repo in repos}
        for future in as_completed(futures):
            repo_name, rows, fetched_count = future.result()
            logger.info("%s: fetched %d commits, keeping %d", repo_name, fetched_count, len(rows))
            total_fetched += fetched_count
            fetched_rows.extend(rows)

    if args.dry_run:
        logger.info("Dry run complete: fetched=%d, new_rows=%d", total_fetched, len(fetched_rows))
        print(f"dry-run fetched={total_fetched} new_rows={len(fetched_rows)}")
        return

    if not fetched_rows:
        logger.info("No new commit rows to insert")
        return

    client = get_clickhouse_client()
    try:
        inserted = 0
        for batch in _chunked(fetched_rows, args.batch_size):
            client.insert("commits", data=batch, column_names=COMMIT_COLUMNS)
            inserted += len(batch)
        logger.info("Inserted %d new commit rows", inserted)
        print(f"inserted={inserted}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
