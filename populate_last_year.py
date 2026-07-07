from __future__ import annotations

import os
import runpy
import shutil
import subprocess
import sys


def _run_inside_container(argv: list[str]) -> int:
    script_path = Path("/app/scripts/populate_last_year.py")
    if script_path.exists():
        sys.argv = [str(script_path), *argv]
        runpy.run_path(str(script_path), run_name="__main__")
        return 0
    raise SystemExit("populate_last_year.py is only available inside the app container at /app/scripts")


def _delegate_to_container(argv: list[str]) -> int:
    if shutil.which("docker") is None:
        raise SystemExit("docker is required to run this script from the host")

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
        "/app/scripts/populate_last_year.py",
        *argv,
    ]
    result = subprocess.run(command, check=False)
    return result.returncode


def main() -> None:
    argv = sys.argv[1:]
    if os.getenv("VIGIL_IN_CONTAINER") == "1":
        raise SystemExit(_run_inside_container(argv))
    raise SystemExit(_delegate_to_container(argv))


if __name__ == "__main__":
    main()
