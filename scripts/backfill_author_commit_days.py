from __future__ import annotations

import logging
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.client import get_clickhouse_client
from app.core.config import settings


logger = logging.getLogger("vigil.backfill_author_days")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)

    client = get_clickhouse_client()
    try:
        client.command("TRUNCATE TABLE author_commit_days")
        client.command(
            "INSERT INTO author_commit_days (author_login, day, total) "
            f"SELECT author_login, day, count() AS total FROM ("
            f"SELECT {settings.canonical_author_login_expr()} AS author_login, toDate(committed_at) AS day FROM commits"
            f") AS source GROUP BY author_login, day"
        )
        logger.info("Backfilled author_commit_days from commits")
    finally:
        client.close()


if __name__ == "__main__":
    main()
