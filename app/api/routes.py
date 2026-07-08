from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import enforce_rate_limit, require_api_key
from app.flow.flow import vigil_sync
from app.services.github_contributions import (
    get_contribution_daily_totals,
    get_contribution_streak,
    get_total_contributions,
    get_viewer_login,
)
from app.services.client import get_clickhouse_client

router = APIRouter(prefix="/api", tags=["vigil"], dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])


class RepoOut(BaseModel):
    full_name: str
    name: str
    owner: str
    is_org: bool
    private: bool
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


class HourlyTotalOut(BaseModel):
    period: datetime
    total: int


class RepoTotalOut(BaseModel):
    repo: str
    total: int


class MergeRatioOut(BaseModel):
    repo: str | None = None
    total: int
    merge_commits: int
    regular_commits: int
    merge_ratio: float


class AuthorStreakOut(BaseModel):
    author_login: str
    current_streak: int
    longest_streak: int
    last_active_day: date | None
    active_days: int


class AuthorPeriodTotalOut(BaseModel):
    period: date
    author_login: str
    total: int


class DailyAuthorStatsOut(BaseModel):
    total: list[PeriodTotalOut]
    by_author: list[AuthorPeriodTotalOut]

def _author_login_filter(author_login: str | None) -> tuple[str, dict[str, str]]:
    if not author_login:
        return "", {}
    aliases = settings.author_login_aliases(author_login)
    if len(aliases) == 1:
        return "WHERE author_login = %(author_login)s", {"author_login": aliases[0]}
    quoted_aliases = ", ".join(f"'{alias}'" for alias in aliases)
    return f"WHERE author_login IN ({quoted_aliases})", {}


class OverviewOut(BaseModel):
    total_commits: int
    total_repos: int
    total_authors: int
    busiest_day: PeriodTotalOut | None
    most_active_repo: RepoTotalOut | None


class DailyStatsOut(BaseModel):
    total: list[PeriodTotalOut]
    by_repo: list[RepoPeriodTotalOut]


class MonthlyStatsOut(BaseModel):
    total: list[PeriodTotalOut]
    by_repo: list[RepoPeriodTotalOut]


class FlowRunOut(BaseModel):
    status: str
    detail: str


def _stats_where(repo: str | None = None, clause: str = "repo = %(repo)s") -> tuple[str, dict[str, str]]:
    params: dict[str, str] = {}
    where = ""
    if repo:
        where = f"WHERE {clause}"
        params["repo"] = repo
    return where, params


def _query_dicts(sql: str, parameters: dict | None = None):
    client = get_clickhouse_client()
    try:
        result = client.query(sql, parameters=parameters)
        columns = list(result.column_names)
        return [dict(zip(columns, row)) for row in result.result_rows]
    finally:
        client.close()


def _unique_commits(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique_rows: list[dict] = []
    for row in rows:
        key = (row["repo"], row["sha"])
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hourly_range_from_rows(rows: list[dict], since: datetime, until: datetime) -> list[HourlyTotalOut]:
    start_hour = _to_utc(since).replace(minute=0, second=0, microsecond=0)
    end_utc = _to_utc(until)
    end_hour = end_utc.replace(minute=0, second=0, microsecond=0)
    if end_utc != end_hour:
        end_hour += timedelta(hours=1)

    totals: dict[datetime, int] = {}
    for row in rows:
        period = row["period"]
        if period.tzinfo is None:
            period = period.replace(tzinfo=timezone.utc)
        else:
            period = period.astimezone(timezone.utc)
        totals[period.replace(minute=0, second=0, microsecond=0)] = int(row["total"])

    result: list[HourlyTotalOut] = []
    current = start_hour
    while current < end_hour:
        result.append(HourlyTotalOut(period=current, total=totals.get(current, 0)))
        current += timedelta(hours=1)

    return result


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
    rows = _query_dicts("SELECT full_name, name, owner, is_org, private, default_branch FROM repos ORDER BY full_name")
    return [RepoOut.model_validate(row) for row in rows]


@router.get("/repos/{repo_full_name:path}/sync-state", response_model=SyncStateOut)
def read_sync_state(repo_full_name: str):
    rows = _query_dicts(
        "SELECT repo, last_synced_sha, last_synced_at, last_run_status, last_run_at "
        "FROM sync_state WHERE repo = %(repo)s",
        {"repo": repo_full_name},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No sync state found for {repo_full_name}")
    return SyncStateOut.model_validate(rows[0])


@router.get("/commits", response_model=list[CommitOut])
def list_commits(
    repo: str | None = None,
    author_login: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    where, params = _stats_where(repo)
    author_filter, author_params = _author_login_filter(author_login)
    if author_filter:
        where = f"{where} AND {author_filter.removeprefix('WHERE ')}" if where else author_filter
        params.update(author_params)
    rows = _query_dicts(
        f"SELECT repo, sha, author_login, author_name, author_email, message, is_merge, committed_at "
        f"FROM commits {where} ORDER BY committed_at DESC LIMIT {limit}",
        params or None,
    )
    return [CommitOut.model_validate(row) for row in rows]


@router.get("/stats/daily", response_model=DailyStatsOut)
def daily_stats(repo: str | None = None):
    if repo is None:
        try:
            viewer_login = settings.canonical_author_login(get_viewer_login())
            totals = get_contribution_daily_totals(viewer_login, start_year=2022)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return DailyStatsOut(
            total=[PeriodTotalOut.model_validate(item.__dict__) for item in sorted(totals, key=lambda item: item.period, reverse=True)],
            by_repo=[],
        )

    where, params = _stats_where(repo)
    totals = _query_dicts(
        f"SELECT toDate(committed_at) AS period, uniqExact(sha) AS total FROM commits {where} GROUP BY period ORDER BY period DESC",
        params or None,
    )
    by_repo = _query_dicts(
        f"SELECT toDate(committed_at) AS period, repo, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, period ORDER BY period DESC, repo",
        params or None,
    )
    return DailyStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_repo=[RepoPeriodTotalOut.model_validate(row) for row in by_repo],
    )


@router.get("/stats/daily/{repo_full_name:path}", response_model=DailyStatsOut)
def daily_stats_for_repo(repo_full_name: str):
    return daily_stats(repo_full_name)


@router.get("/stats/daily/authors", response_model=DailyAuthorStatsOut)
def daily_author_stats(days: int = Query(default=7, ge=1, le=365), author_login: str | None = None):
    params: dict[str, int | str] = {"days": days}
    where = "WHERE toDate(committed_at) >= today() - %(days)s"
    author_filter, author_params = _author_login_filter(author_login)
    if author_filter:
        where += f" AND {author_filter.removeprefix('WHERE ')}"
        params.update(author_params)

    totals = _query_dicts(
        f"SELECT toDate(committed_at) AS period, uniqExact(sha) AS total FROM commits {where} GROUP BY period ORDER BY period DESC",
        params,
    )
    by_author = _query_dicts(
        f"SELECT toDate(committed_at) AS period, {settings.canonical_author_login_expr()} AS author_login, uniqExact(sha) AS total FROM commits {where} GROUP BY period, author_login ORDER BY period DESC, author_login",
        params,
    )
    return DailyAuthorStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_author=[AuthorPeriodTotalOut.model_validate(row) for row in by_author],
    )


@router.get("/stats/monthly", response_model=MonthlyStatsOut)
def monthly_stats(repo: str | None = None):
    where, params = _stats_where(repo)
    totals = _query_dicts(
        f"SELECT toStartOfMonth(committed_at) AS period, uniqExact(sha) AS total FROM commits {where} GROUP BY period ORDER BY period DESC",
        params or None,
    )
    by_repo = _query_dicts(
        f"SELECT toStartOfMonth(committed_at) AS period, repo, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, period ORDER BY period DESC, repo",
        params or None,
    )
    return MonthlyStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_repo=[RepoPeriodTotalOut.model_validate(row) for row in by_repo],
    )


@router.get("/stats/monthly/{repo_full_name:path}", response_model=MonthlyStatsOut)
def monthly_stats_for_repo(repo_full_name: str):
    return monthly_stats(repo_full_name)


@router.get("/stats/authors", response_model=list[AuthorCommitCountOut])
def author_stats(repo: str | None = None):
    where, params = _stats_where(repo)
    rows = _query_dicts(
        f"SELECT repo, {settings.canonical_author_login_expr()} AS author_login, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, author_login ORDER BY total DESC, repo, author_login",
        params or None,
    )
    return [AuthorCommitCountOut.model_validate(row) for row in rows]


@router.get("/stats/authors/{repo_full_name:path}", response_model=list[AuthorCommitCountOut])
def author_stats_for_repo(repo_full_name: str):
    return author_stats(repo_full_name)


@router.get("/stats/hourly", response_model=list[HourlyActivityOut])
def hourly_stats(repo: str | None = None):
    where, params = _stats_where(repo)
    rows = _query_dicts(
        f"SELECT repo, toHour(committed_at) AS hour, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, hour ORDER BY repo, hour",
        params or None,
    )
    return [HourlyActivityOut.model_validate(row) for row in rows]


@router.get("/stats/hourly/authors", response_model=list[HourlyActivityOut])
def hourly_stats_for_author(author_login: str = Query(..., min_length=1), repo: str | None = None):
    where, params = _stats_where(repo)
    author_filter, author_params = _author_login_filter(author_login)
    if author_filter:
        where = f"{where} AND {author_filter.removeprefix('WHERE ')}" if where else author_filter
        params.update(author_params)

    rows = _query_dicts(
        f"SELECT repo, toHour(committed_at) AS hour, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, hour ORDER BY repo, hour",
        params or None,
    )
    return [HourlyActivityOut.model_validate(row) for row in rows]


@router.get("/stats/hourly/authors/range", response_model=list[HourlyTotalOut])
def hourly_stats_for_author_range(
    author_login: str = Query(..., min_length=1),
    since: datetime = Query(...),
    until: datetime = Query(...),
    repo: str | None = None,
):
    if since > until:
        raise HTTPException(status_code=400, detail="since must be before until")

    since_utc = _to_utc(since)
    until_utc = _to_utc(until)
    if until_utc.minute or until_utc.second or until_utc.microsecond:
        until_utc = until_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        until_utc = until_utc.replace(minute=0, second=0, microsecond=0)

    since_utc = since_utc.replace(minute=0, second=0, microsecond=0)

    clauses: list[str] = ["committed_at >= %(since)s", "committed_at < %(until)s"]
    params: dict[str, datetime | str] = {"since": since_utc, "until": until_utc}

    if repo:
        clauses.append("repo = %(repo)s")
        params["repo"] = repo

    author_filter, author_params = _author_login_filter(author_login)
    if author_filter:
        clauses.append(author_filter.removeprefix("WHERE "))
        params.update(author_params)

    where = f"WHERE {' AND '.join(clauses)}"
    rows = _query_dicts(
        f"SELECT toStartOfHour(committed_at) AS period, uniqExact(sha) AS total FROM commits {where} GROUP BY period ORDER BY period",
        params,
    )
    return _hourly_range_from_rows(rows, since_utc, until_utc)


@router.get("/stats/hourly/{repo_full_name:path}", response_model=list[HourlyActivityOut])
def hourly_stats_for_repo(repo_full_name: str):
    return hourly_stats(repo_full_name)


@router.get("/stats/weekly", response_model=DailyStatsOut)
def weekly_stats(repo: str | None = None):
    where, params = _stats_where(repo)
    totals = _query_dicts(
        f"SELECT toStartOfWeek(committed_at) AS period, uniqExact(sha) AS total FROM commits {where} GROUP BY period ORDER BY period DESC",
        params or None,
    )
    by_repo = _query_dicts(
        f"SELECT toStartOfWeek(committed_at) AS period, repo, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, period ORDER BY period DESC, repo",
        params or None,
    )
    return DailyStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_repo=[RepoPeriodTotalOut.model_validate(row) for row in by_repo],
    )


@router.get("/stats/yearly", response_model=MonthlyStatsOut)
def yearly_stats(repo: str | None = None):
    where, params = _stats_where(repo)
    totals = _query_dicts(
        f"SELECT toStartOfYear(committed_at) AS period, uniqExact(sha) AS total FROM commits {where} GROUP BY period ORDER BY period DESC",
        params or None,
    )
    by_repo = _query_dicts(
        f"SELECT toStartOfYear(committed_at) AS period, repo, uniqExact(sha) AS total FROM commits {where} GROUP BY repo, period ORDER BY period DESC, repo",
        params or None,
    )
    return MonthlyStatsOut(
        total=[PeriodTotalOut.model_validate(row) for row in totals],
        by_repo=[RepoPeriodTotalOut.model_validate(row) for row in by_repo],
    )


@router.get("/stats/top-repos", response_model=list[RepoTotalOut])
def top_repos(limit: int = Query(default=10, ge=1, le=100), repo: str | None = None):
    where, params = _stats_where(repo)
    rows = _query_dicts(
        f"SELECT repo, uniqExact(sha) AS total FROM commits {where} GROUP BY repo ORDER BY total DESC, repo LIMIT {limit}",
        params or None,
    )
    return [RepoTotalOut.model_validate(row) for row in rows]


@router.get("/stats/merge-ratio", response_model=MergeRatioOut)
def merge_ratio(repo: str | None = None):
    where, params = _stats_where(repo)
    rows = _query_dicts(
        f"SELECT uniqExact(sha) AS total, uniqExactIf(sha, is_merge) AS merge_commits, uniqExactIf(sha, NOT is_merge) AS regular_commits FROM commits {where}",
        params or None,
    )
    row = rows[0] if rows else {"total": 0, "merge_commits": 0, "regular_commits": 0}
    total = int(row["total"])
    merge_commits = int(row["merge_commits"])
    regular_commits = int(row["regular_commits"])
    return MergeRatioOut(
        repo=repo,
        total=total,
        merge_commits=merge_commits,
        regular_commits=regular_commits,
        merge_ratio=(merge_commits / total) if total else 0.0,
    )


@router.get("/stats/overview", response_model=OverviewOut)
def overview_stats():
    try:
        total_commits = get_total_contributions(settings.canonical_author_login(get_viewer_login()), start_year=2022)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    totals = _query_dicts(
        f"SELECT uniqExactIf({settings.canonical_author_login_expr()}, {settings.canonical_author_login_expr()} != '') AS total_authors FROM commits"
    )
    repos = _query_dicts("SELECT count() AS total_repos FROM repos")
    busiest_day = _query_dicts(
        "SELECT toDate(committed_at) AS period, uniqExact(sha) AS total FROM commits GROUP BY period ORDER BY total DESC, period DESC LIMIT 1"
    )
    most_active_repo = _query_dicts(
        "SELECT repo, uniqExact(sha) AS total FROM commits GROUP BY repo ORDER BY total DESC, repo LIMIT 1"
    )

    total_row = totals[0] if totals else {"total_authors": 0}
    repo_row = repos[0] if repos else {"total_repos": 0}

    return OverviewOut(
        total_commits=int(total_commits),
        total_repos=int(repo_row["total_repos"]),
        total_authors=int(total_row["total_authors"]),
        busiest_day=PeriodTotalOut.model_validate(busiest_day[0]) if busiest_day else None,
        most_active_repo=RepoTotalOut.model_validate(most_active_repo[0]) if most_active_repo else None,
    )


@router.get("/stats/activity-range", response_model=list[CommitOut])
def activity_range(
    since: datetime | None = None,
    until: datetime | None = None,
    repo: str | None = None,
):
    if since and until and since > until:
        raise HTTPException(status_code=400, detail="since must be before until")

    clauses: list[str] = []
    params: dict[str, datetime | str] = {}

    if repo:
        clauses.append("repo = %(repo)s")
        params["repo"] = repo
    if since:
        clauses.append("committed_at >= %(since)s")
        params["since"] = since
    if until:
        clauses.append("committed_at <= %(until)s")
        params["until"] = until

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _query_dicts(
        f"SELECT repo, sha, author_login, author_name, author_email, message, is_merge, committed_at FROM commits {where} ORDER BY committed_at DESC",
        params or None,
    )
    return [CommitOut.model_validate(row) for row in _unique_commits(rows)]


@router.get("/stats/streak/{author_login}", response_model=AuthorStreakOut)
def author_streak(author_login: str):
    try:
        streak = get_contribution_streak(settings.canonical_author_login(author_login))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return AuthorStreakOut.model_validate(streak.__dict__)
