from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.security import enforce_rate_limit, require_api_key
from app.flow.flow import vigil_sync
from app.services.client import get_clickhouse_client

router = APIRouter(prefix="/api", tags=["vigil"], dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])


class RepoOut(BaseModel):
    name: str
    owner: str
    default_branch: str


class SyncStateOut(BaseModel):
    repo: str
    last_synced_sha: str
    last_synced_at: datetime
    last_run_status: str
    last_run_at: datetime


class CommitOut(BaseModel):
    repo: str
    sha: str
    author_login: str
    author_name: str
    author_email: str
    message: str | None
    is_merge: bool
    committed_at: datetime


class PeriodTotalOut(BaseModel):
    period: date
    total: int


class RepoPeriodTotalOut(BaseModel):
    period: date
    repo: str
    total: int


class AuthorCommitCountOut(BaseModel):
    repo: str
    author_login: str
    total: int


class HourlyActivityOut(BaseModel):
    repo: str
    hour: int
    total: int


class DailyStatsOut(BaseModel):
    total: list[PeriodTotalOut]
    by_repo: list[RepoPeriodTotalOut]


class MonthlyStatsOut(BaseModel):
    total: list[PeriodTotalOut]
    by_repo: list[RepoPeriodTotalOut]


class FlowRunOut(BaseModel):
    status: str
    detail: str


def _query_dicts(sql: str, parameters: dict | None = None):
    client = get_clickhouse_client()
    try:
        result = client.query(sql, parameters=parameters)
        columns = list(result.column_names)
        return [dict(zip(columns, row)) for row in result.result_rows]
    finally:
        client.close()


@router.get("/")
def root():
    return {"service": "vigil", "status": "ok"}


@router.post("/flow/run", response_model=FlowRunOut, status_code=202)
def trigger_flow(background_tasks: BackgroundTasks):
    def _run() -> None:
        vigil_sync()

    background_tasks.add_task(_run)
    return FlowRunOut(status="queued", detail="Prefect flow queued")


@router.get("/repos", response_model=list[RepoOut])
def list_repos():
    rows = _query_dicts("SELECT name, owner, default_branch FROM repos ORDER BY name")
    return [RepoOut.model_validate(row) for row in rows]


@router.get("/repos/{repo_name}/sync-state", response_model=SyncStateOut)
def read_sync_state(repo_name: str):
    rows = _query_dicts(
        "SELECT repo, last_synced_sha, last_synced_at, last_run_status, last_run_at "
        "FROM sync_state WHERE repo = %(repo)s",
        {"repo": repo_name},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No sync state found for {repo_name}")
    return SyncStateOut.model_validate(rows[0])


@router.get("/commits", response_model=list[CommitOut])
def list_commits(repo: str | None = None, limit: int = Query(default=100, ge=1, le=1000)):
    params: dict[str, str] = {}
    where = ""
    if repo:
        where = "WHERE repo = %(repo)s"
        params["repo"] = repo
    rows = _query_dicts(
        f"SELECT repo, sha, author_login, author_name, author_email, message, is_merge, committed_at "
        f"FROM commits {where} ORDER BY committed_at DESC LIMIT {limit}",
        params or None,
    )
    return [CommitOut.model_validate(row) for row in rows]


@router.get("/stats/daily", response_model=DailyStatsOut)
def daily_stats(repo: str | None = None):
    params: dict[str, str] = {}
    where = ""
    if repo:
        where = "WHERE repo = %(repo)s"
        params["repo"] = repo
    totals = _query_dicts(
        f"SELECT day AS period, sum(total) AS total FROM commits_per_day {where} GROUP BY day ORDER BY period DESC",
        params or None,
    )
    by_repo = _query_dicts(
        f"SELECT day AS period, repo, total FROM commits_per_day {where} ORDER BY period DESC, repo",
        params or None,
    )
    return DailyStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_repo=[RepoPeriodTotalOut.model_validate(row) for row in by_repo],
    )


@router.get("/stats/monthly", response_model=MonthlyStatsOut)
def monthly_stats(repo: str | None = None):
    params: dict[str, str] = {}
    where = ""
    if repo:
        where = "WHERE repo = %(repo)s"
        params["repo"] = repo
    totals = _query_dicts(
        f"SELECT month AS period, sum(total) AS total FROM commits_per_month {where} GROUP BY month ORDER BY period DESC",
        params or None,
    )
    by_repo = _query_dicts(
        f"SELECT month AS period, repo, total FROM commits_per_month {where} ORDER BY period DESC, repo",
        params or None,
    )
    return MonthlyStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_repo=[RepoPeriodTotalOut.model_validate(row) for row in by_repo],
    )


@router.get("/stats/authors", response_model=list[AuthorCommitCountOut])
def author_stats(repo: str | None = None):
    params: dict[str, str] = {}
    where = ""
    if repo:
        where = "WHERE repo = %(repo)s"
        params["repo"] = repo
    rows = _query_dicts(
        f"SELECT repo, author_login, total FROM author_commit_counts {where} ORDER BY total DESC, repo, author_login",
        params or None,
    )
    return [AuthorCommitCountOut.model_validate(row) for row in rows]


@router.get("/stats/hourly", response_model=list[HourlyActivityOut])
def hourly_stats(repo: str | None = None):
    params: dict[str, str] = {}
    where = ""
    if repo:
        where = "WHERE repo = %(repo)s"
        params["repo"] = repo
    rows = _query_dicts(
        f"SELECT repo, hour, total FROM hourly_activity {where} ORDER BY repo, hour",
        params or None,
    )
    return [HourlyActivityOut.model_validate(row) for row in rows]
