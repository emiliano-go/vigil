from __future__ import annotations

import os
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def _wait_for_http(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    request = Request(url, headers=headers or {})

    while True:
        try:
            with urlopen(request, timeout=5):
                return
        except URLError:
            if time.time() >= deadline:
                raise TimeoutError(f"Timed out waiting for {url}")
            time.sleep(2)


def _wait_for_dependencies() -> None:
    clickhouse_host = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
    clickhouse_port = os.environ.get("CLICKHOUSE_PORT", "8123")
    prefect_api_url = os.environ.get("PREFECT_API_URL", "")

    _wait_for_http(f"http://{clickhouse_host}:{clickhouse_port}/ping")

    if prefect_api_url:
        _wait_for_http(f"{prefect_api_url.rstrip('/')}/health")


def main() -> None:
    _wait_for_dependencies()

    subprocess.run(["dbwarden", "migrate"], check=True)
    subprocess.run(["uv", "run", "python", "scripts/backfill_author_commit_days.py"], check=True)

    root_path = os.environ.get("ROOT_PATH", "").strip()
    uvicorn_args = [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        os.environ.get("PORT", "8000"),
        "--workers",
        "1",
    ]
    if root_path:
        uvicorn_args.extend(["--root-path", root_path])

    os.execvp(
        "uvicorn",
        uvicorn_args,
    )


if __name__ == "__main__":
    main()
