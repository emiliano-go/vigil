import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass(frozen=True)
class Settings:
    clickhouse_user: str = ""
    clickhouse_password: str = ""
    clickhouse_db: str = "default"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_native_port: int = 9000
    github_user_token: str = ""
    prefect_api_url: str = ""
    root_path: str = ""
    api_key: str = ""
    rate_limit: str = "60/minute"
    author_login_canonical_map: dict[str, str] = None  # type: ignore[assignment]

    def __init__(self) -> None:
        import os

        object.__setattr__(self, "clickhouse_user", os.getenv("CLICKHOUSE_USER", ""))
        object.__setattr__(self, "clickhouse_password", os.getenv("CLICKHOUSE_PASSWORD", ""))
        object.__setattr__(self, "clickhouse_db", os.getenv("CLICKHOUSE_DB", "default"))
        object.__setattr__(self, "clickhouse_host", os.getenv("CLICKHOUSE_HOST", "localhost"))
        object.__setattr__(self, "clickhouse_port", int(os.getenv("CLICKHOUSE_PORT", "8123")))
        object.__setattr__(self, "clickhouse_native_port", int(os.getenv("CLICKHOUSE_NATIVE_PORT", "9000")))
        object.__setattr__(self, "github_user_token", os.getenv("GITHUB_TOKEN", ""))
        object.__setattr__(self, "prefect_api_url", os.getenv("PREFECT_API_URL", ""))
        object.__setattr__(self, "root_path", os.getenv("ROOT_PATH", ""))
        object.__setattr__(self, "api_key", os.getenv("API_KEY", ""))
        object.__setattr__(self, "rate_limit", os.getenv("RATE_LIMIT", "60/minute"))
        object.__setattr__(self, "author_login_canonical_map", self._load_login_map(os.getenv("AUTHOR_LOGIN_CANONICAL_MAP", "{}")))

    @property
    def clickhouse_http_url(self) -> str:
        return (
            f"http://{self.clickhouse_user}:{self.clickhouse_password}"
            f"@{self.clickhouse_host}:{self.clickhouse_port}/{self.clickhouse_db}"
        )

    @property
    def clickhouse_native_url(self) -> str:
        return (
            f"clickhouse://{self.clickhouse_user}:{self.clickhouse_password}"
            f"@{self.clickhouse_host}:{self.clickhouse_native_port}/{self.clickhouse_db}"
        )

    @property
    def clickhouse_async_url(self) -> str:
        return (
            f"http://{self.clickhouse_user}:{self.clickhouse_password}"
            f"@{self.clickhouse_host}:{self.clickhouse_port}/{self.clickhouse_db}"
        )

    @staticmethod
    def _load_login_map(raw: str) -> dict[str, str]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        if not isinstance(data, dict):
            return {}

        return {str(alias): str(canonical) for alias, canonical in data.items() if alias and canonical}

    def canonical_author_login(self, author_login: str) -> str:
        return self.author_login_canonical_map.get(author_login, author_login)

    def author_login_aliases(self, author_login: str) -> list[str]:
        canonical = self.canonical_author_login(author_login)
        aliases = [alias for alias, mapped in self.author_login_canonical_map.items() if mapped == canonical]
        if canonical not in aliases:
            aliases.append(canonical)
        return aliases

    def canonical_author_login_expr(self, column: str = "author_login") -> str:
        if not self.author_login_canonical_map:
            return column

        clauses: list[str] = []
        for alias, canonical in self.author_login_canonical_map.items():
            clauses.append(f"{column} = '{alias}'")
            clauses.append(f"'{canonical}'")

        pairs = ", ".join(clauses)
        return f"multiIf({pairs}, {column})"


settings = Settings()
