from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


_source_file = globals().get("__file__")
if _source_file and _source_file not in {"-", "<stdin>"}:
    ROOT = Path(_source_file).resolve().parents[1]
else:
    ROOT = Path("/app") if os.getenv("VIGIL_IN_CONTAINER") == "1" else Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.client import get_clickhouse_client
from app.services.github_contributions import get_contribution_daily_totals, get_viewer_login


logger = logging.getLogger("vigil.repair_author_commit_days")

TABLE = "author_commit_days"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair author_commit_days for one author from GitHub contributions.")
    parser.add_argument("--author-login", default=None, help="Canonical GitHub login to repair. Defaults to the viewer login.")
    parser.add_argument("--since", default="2022-01-01", help="Repair days since this date (YYYY-MM-DD or ISO datetime).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without inserting rows.")
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
        "scripts/repair_author_commit_days.py",
        *argv,
    ]
    result = subprocess.run(command, check=False)
    return result.returncode


def _parse_since(raw: str) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _negate_existing_rows(client, author_login: str, since: datetime) -> list[list]:
    rows = client.query(
        "SELECT author_login, day, total FROM author_commit_days WHERE author_login = %(author_login)s AND day >= %(since)s ORDER BY day",
        parameters={"author_login": author_login, "since": since.date()},
    ).result_rows
    return [[author_login, row[1], -int(row[2])] for row in rows]


def _github_rows(author_login: str, since: datetime) -> list[list]:
    daily = get_contribution_daily_totals(author_login, start_year=since.year)
    return [
        [author_login, item.period, int(item.total)]
        for item in daily
        if item.period >= since.date() and item.total > 0
    ]


def _run_local(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)

    since = _parse_since(args.since)
    author_login = args.author_login or settings.canonical_author_login(get_viewer_login())
    author_login = settings.canonical_author_login(author_login)

    client = get_clickhouse_client()
    try:
        negate_rows = _negate_existing_rows(client, author_login, since)
    finally:
        client.close()

    github_rows = _github_rows(author_login, since)

    logger.info(
        "Repairing %s since %s: negating %d existing rows, inserting %d GitHub rows",
        author_login,
        since.isoformat(),
        len(negate_rows),
        len(github_rows),
    )

    if args.dry_run:
        preview_dates = [row[1].isoformat() for row in github_rows if row[2] > 0][:10]
        print(f"dry-run author={author_login} negate_rows={len(negate_rows)} github_rows={len(github_rows)} preview={preview_dates}")
        return 0

    client = get_clickhouse_client()
    try:
        if negate_rows:
            client.insert(TABLE, data=negate_rows, column_names=["author_login", "day", "total"])
        if github_rows:
            client.insert(TABLE, data=github_rows, column_names=["author_login", "day", "total"])
        print(f"repaired author={author_login} negate_rows={len(negate_rows)} github_rows={len(github_rows)}")
        logger.info("Repair complete for %s", author_login)
    finally:
        client.close()

    return 0


def main() -> None:
    if _should_delegate_to_container():
        raise SystemExit(_delegate_to_container(sys.argv[1:]))

    raise SystemExit(_run_local(sys.argv[1:]))


if __name__ == "__main__":
    main()
