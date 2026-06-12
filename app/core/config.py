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
    clickhouse_http_port: int = 8123
    clickhouse_native_port: int = 9000

    def __init__(self) -> None:
        import os

        object.__setattr__(self, "clickhouse_user", os.getenv("CLICKHOUSE_USER", ""))
        object.__setattr__(self, "clickhouse_password", os.getenv("CLICKHOUSE_PASSWORD", ""))
        object.__setattr__(self, "clickhouse_db", os.getenv("CLICKHOUSE_DB", "default"))
        object.__setattr__(self, "clickhouse_host", os.getenv("CLICKHOUSE_HOST", "localhost"))
        object.__setattr__(self, "clickhouse_http_port", int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123")))
        object.__setattr__(self, "clickhouse_native_port", int(os.getenv("CLICKHOUSE_NATIVE_PORT", "9000")))

    @property
    def clickhouse_http_url(self) -> str:
        return (
            f"http://{self.clickhouse_user}:{self.clickhouse_password}"
            f"@{self.clickhouse_host}:{self.clickhouse_http_port}"
        )

    @property
    def clickhouse_native_url(self) -> str:
        return (
            f"clickhouse://{self.clickhouse_user}:{self.clickhouse_password}"
            f"@{self.clickhouse_host}:{self.clickhouse_native_port}/{self.clickhouse_db}"
        )

    @property
    def clickhouse_async_url(self) -> str:
        return self.clickhouse_http_url


settings = Settings()
