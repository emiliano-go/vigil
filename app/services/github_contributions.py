from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_GRAPHQL_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class ContributionStreak:
    author_login: str
    current_streak: int
    longest_streak: int
    last_active_day: date | None
    active_days: int


@dataclass(frozen=True)
class DailyContribution:
    period: date
    total: int


def _github_graphql(query: str, variables: dict[str, str]) -> dict:
    if not settings.github_user_token:
        raise RuntimeError("GITHUB_TOKEN is required to read GitHub contribution data")

    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        GITHUB_GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.github_user_token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "vigil",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=GITHUB_GRAPHQL_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"GitHub GraphQL request failed: {exc}") from exc

    data = json.loads(body)
    if data.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {data['errors']}")

    return data["data"]


@lru_cache(maxsize=1)
def get_viewer_login() -> str:
    data = _github_graphql("query { viewer { login } }", {})
    viewer = data.get("viewer")
    if not viewer or not viewer.get("login"):
        raise RuntimeError("Unable to resolve GitHub viewer login")
    return viewer["login"]


def _streak_from_days(days: list[date], author_login: str) -> ContributionStreak:
    active_days = sorted(set(days))
    if not active_days:
        return ContributionStreak(author_login=author_login, current_streak=0, longest_streak=0, last_active_day=None, active_days=0)

    active_set = set(active_days)
    longest = 0
    current_run = 0
    current = 0
    previous_day: date | None = None

    for day in active_days:
        if previous_day is not None and day == previous_day + timedelta(days=1):
            current_run += 1
        else:
            current_run = 1
        previous_day = day
        longest = max(longest, current_run)

    today = datetime.now(timezone.utc).date()
    probe = today
    while probe in active_set:
        current += 1
        probe -= timedelta(days=1)

    return ContributionStreak(
        author_login=author_login,
        current_streak=current,
        longest_streak=longest,
        last_active_day=active_days[-1],
        active_days=len(active_days),
    )


def _streak_from_calendar(daily: list[DailyContribution], author_login: str) -> ContributionStreak:
    active_days = sorted({item.period for item in daily if item.total > 0})
    if not active_days:
        return ContributionStreak(author_login=author_login, current_streak=0, longest_streak=0, last_active_day=None, active_days=0)

    longest = 0
    current_run = 0
    previous_day: date | None = None
    for day in active_days:
        if previous_day is not None and day == previous_day + timedelta(days=1):
            current_run += 1
        else:
            current_run = 1
        previous_day = day
        longest = max(longest, current_run)

    latest_calendar_day = datetime.now(settings.contribution_timezone).date()
    active_set = set(active_days)
    current = 0
    probe = latest_calendar_day
    while probe in active_set:
        current += 1
        probe -= timedelta(days=1)

    return ContributionStreak(
        author_login=author_login,
        current_streak=current,
        longest_streak=longest,
        last_active_day=active_days[-1],
        active_days=len(active_days),
    )


def get_contribution_streak(author_login: str) -> ContributionStreak:
    daily = get_contribution_daily_totals(author_login, start_year=2022)
    return _streak_from_calendar(daily, author_login)


def get_total_contributions(author_login: str, start_year: int = 2022) -> int:
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
          }
        }
      }
    }
    """

    total = 0
    current_year = datetime.now(timezone.utc).year
    for year in range(start_year, current_year + 1):
        from_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime.now(timezone.utc) if year == current_year else datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        data = _github_graphql(
            query,
            {
                "login": author_login,
                "from": from_dt.isoformat().replace("+00:00", "Z"),
                "to": to_dt.isoformat().replace("+00:00", "Z"),
            },
        )
        user = data.get("user")
        if not user:
            raise RuntimeError(f"GitHub user not found: {author_login}")
        total += int(user["contributionsCollection"]["contributionCalendar"]["totalContributions"])

    return total


def get_contribution_daily_totals(author_login: str, start_year: int = 2022) -> list[DailyContribution]:
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    daily: list[DailyContribution] = []
    current_year = datetime.now(timezone.utc).year
    for year in range(start_year, current_year + 1):
        from_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime.now(timezone.utc) if year == current_year else datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        data = _github_graphql(
            query,
            {
                "login": author_login,
                "from": from_dt.isoformat().replace("+00:00", "Z"),
                "to": to_dt.isoformat().replace("+00:00", "Z"),
            },
        )
        user = data.get("user")
        if not user:
            raise RuntimeError(f"GitHub user not found: {author_login}")

        weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for contribution_day in week["contributionDays"]:
                daily.append(
                    DailyContribution(
                        period=date.fromisoformat(contribution_day["date"]),
                        total=int(contribution_day["contributionCount"]),
                    )
                )

    return daily
