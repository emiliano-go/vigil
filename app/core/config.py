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
    api_key: str = ""
    rate_limit: str = "60/minute"

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
        object.__setattr__(self, "api_key", os.getenv("API_KEY", ""))
        object.__setattr__(self, "rate_limit", os.getenv("RATE_LIMIT", "60/minute"))

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


settings = Settings()
