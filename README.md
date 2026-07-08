<p align="center">
  <img src="https://raw.githubusercontent.com/emiliano-go/vigil/refs/heads/master/assets/icon.png" alt="vigil" width="225"/>
</p>
<p align="center">
  <em>Never miss a commit.</em>
</p>
<p align="center">
  <h1 align="center">vigil</h1>
</p>

<p align="center">
  <strong>Personal GitHub activity tracking, on your own infrastructure.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white&style=for-the-badge" alt="Python">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-10AC84?style=for-the-badge" alt="License">
  </a>
  <a href="https://github.com/emiliano-go/vigil/actions/workflows/deploy.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/emiliano-go/vigil/deploy.yml?branch=master&style=for-the-badge&logo=github&label=Deploy" alt="Deploy">
  </a>
  <a href="https://ghcr.io/emiliano-go/vigil">
    <img src="https://img.shields.io/badge/GHCR-latest-2496ED?logo=docker&logoColor=white&style=for-the-badge" alt="GHCR">
  </a>
</p>

---

## Quick start

```python
from app.core.config import settings
from app.services.client import get_clickhouse_client

client = get_clickhouse_client()
rows = client.query("SELECT uniqExact(sha) AS total FROM commits")
print(f"{rows[0][0]} commits tracked")
```

That is it. vigil syncs every 30 minutes — repos indexed, commits fetched,
deduplicated, and stored in ClickHouse. No manual polling, no cache warming.

```python
# Trigger a sync on demand
import requests

requests.post(
    "https://vigil.example.com/api/flow/run",
    headers={"X-API-Key": "your-key"},
)
# {"status": "queued", "detail": "Prefect flow queued"}
```

---

## Why vigil

GitHub's contribution graph is a black box. vigil gives you the raw data
behind it — every commit, every branch, every author — in your own ClickHouse
instance, queryable with SQL and exposed through a REST API.

| What | GitHub gives you | vigil gives you |
|---|---|---|
| Commit history | Web UI, REST with pagination | Full table in ClickHouse |
| Multi-branch commits | Only default branch | All branches, deduped by SHA |
| User rename | Breaks history | `AUTHOR_LOGIN_CANONICAL_MAP` |
| Contribution streak | GraphQL only | GraphQL + derived table |
| Hourly breakdown | Not available | `uniqExact(sha)` per hour |
| Merge ratio | Manual counting | `/api/stats/merge-ratio` |
| Sync cadence | Manual fetch | Every 30 min, Prefect orchestrated |

---

## Features

| Category | What vigil handles |
|---|---|
| **Ingestion** | GitHub REST API pagination, SHA dedup at fetch/insert/sync-boundary, branch cross-contamination prevention |
| **Storage** | ClickHouse MergeTree — `commits`, `repos`, `sync_state`, `author_commit_days` with materialized views |
| **Deduplication** | `uniqExact(sha)` on every stats endpoint — no duplicate commits across branches |
| **Author aliasing** | `AUTHOR_LOGIN_CANONICAL_MAP` env var maps old usernames to current ones, with SQL-level `multiIf` |
| **Orchestration** | Prefect 3.x flow runs every 30 min via FastAPI lifespan, configurable with env vars |
| **REST API** | 20+ endpoints — repos, commits, daily/weekly/monthly/yearly stats, hourly breakdowns, top repos, merge ratio, overview, activity range, author streaks |
| **Auth & rate limiting** | `X-API-Key` header + `slowapi` rate limiting on every public route |
| **Streaks** | GitHub GraphQL source of truth for contribution streaks and daily calendars; ClickHouse derived table for fallback |
| **Health & migrations** | `dbwarden` health router at `/health`, schema migrations at `/db` |
| **Deployment** | Docker Compose (ClickHouse + Prefect server + app), GitHub Actions → GHCR, Traefik ingress ready |
| **Timezone support** | `CONTRIBUTION_TIMEZONE_NAME` configures local-time reporting across all endpoints |

---

## At a glance

```python
# Overview — total commits from GitHub GraphQL, rest from ClickHouse
GET /api/stats/overview
# {
#   "total_commits": 4800,       # GitHub contribution count
#   "total_repos": 24,
#   "total_authors": 3,
#   "busiest_day": {"period": "2026-03-15", "total": 47},
#   "most_active_repo": {"repo": "emiliano-go/vigil", "total": 1200}
# }

# Streak — source of truth is GitHub GraphQL
GET /api/stats/streak/emiliano-go
# {
#   "current_streak": 45,
#   "longest_streak": 45,
#   "last_active_day": "2026-07-08",
#   "active_days": 321
# }

# Hourly breakdown for a specific author and window
GET /api/stats/hourly/authors/range?author_login=emiliano-go&since=2026-07-07T00:00:00Z&until=2026-07-08T00:00:00Z
# Returns exactly 24 buckets, [since, until) semantics

# Hourly activity per repo
GET /api/stats/hourly
# [{"repo": "vigil", "hour": 14, "total": 12}, ...]

# Daily stats — uses GitHub GraphQL when no repo filter, else ClickHouse
GET /api/stats/daily
# {"total": [{"period": "2026-07-08", "total": 8}, ...], "by_repo": [...]}

# Weekly / monthly / yearly aggregated
GET /api/stats/weekly
GET /api/stats/monthly
GET /api/stats/yearly

# Merge ratio
GET /api/stats/merge-ratio
# {"total": 4200, "merge_commits": 312, "regular_commits": 3888, "merge_ratio": 0.074}

# Top repos by commit count
GET /api/stats/top-repos?limit=5

# Activity range with deduped commits
GET /api/stats/activity-range?since=2026-07-01T00:00:00Z&until=2026-07-08T00:00:00Z

# Author stats per repo
GET /api/stats/authors
# [{"repo": "vigil", "author_login": "emiliano-go", "total": 843}, ...]

# List commits with optional filters
GET /api/commits?repo=vigil&author_login=emiliano-go&limit=50

# Trigger sync
POST /api/flow/run
```

All endpoints require `X-API-Key` header. Rate limit is configurable via
`RATE_LIMIT` env var (default `60/minute`).

---

## Installation

```bash
# Clone
git clone https://github.com/emiliano-go/vigil.git
cd vigil

# Copy and edit environment
cp .env.example .env

# Start everything
docker compose up -d
```

The stack starts three services:

| Service | Image | Purpose |
|---|---|---|
| `clickhouse` | `clickhouse/clickhouse-server:24.8` | Commit storage, materialized views, aggregations |
| `prefect-server` | `prefecthq/prefect:3-latest` | Flow orchestration, task scheduling |
| `app` | `ghcr.io/emiliano-go/vigil:latest` | FastAPI REST API, sync scheduler, migrations |

The app automatically:
1. Waits for ClickHouse and Prefect to be healthy
2. Runs `dbwarden migrate` for schema creation
3. Backfills the `author_commit_days` derived table
4. Starts the FastAPI server and begins the 30-minute sync loop

### Environment

| Variable | Default | Description |
|---|---|---|
| `CLICKHOUSE_USER` | `app` | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | — | ClickHouse password |
| `CLICKHOUSE_DB` | `default` | ClickHouse database |
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse hostname |
| `CLICKHOUSE_PORT` | `8123` | ClickHouse HTTP port |
| `CLICKHOUSE_NATIVE_PORT` | `9000` | ClickHouse native port |
| `GITHUB_TOKEN` | — | Personal access token with `repo` scope |
| `PREFECT_API_URL` | — | Prefect server API URL |
| `ROOT_PATH` | — | URL prefix when behind a reverse proxy |
| `API_KEY` | — | Required on all requests via `X-API-Key` |
| `RATE_LIMIT` | `60/minute` | Rate limit string for slowapi |
| `AUTHOR_LOGIN_CANONICAL_MAP` | `{}` | JSON alias map, e.g. `{"old":"new"}` |
| `CONTRIBUTION_TIMEZONE_NAME` | `America/Montevideo` | Timezone for hourly/weekly reporting |

---

## Framework support

| Environment | Integration |
|---|---|
| **Docker Compose** | `docker compose up -d` — ClickHouse, Prefect, and app pre-wired |
| **Traefik** | Set `ROOT_PATH` for path-prefixed routing, no host port publishing needed |
| **GitHub Actions** | Push to `master` triggers GHCR build + deploy via `deploy.yml` |
| **Standalone** | Run `uvicorn app.main:app` after starting ClickHouse and Prefect manually |

---

## Testing

Run the test suite (no external services needed for unit tests):

```bash
uv sync --frozen
uv run pytest --cov=app tests/
```

### What is tested

| Test file | What it verifies |
|---|---|
| `test_hourly_range.py` | Exactly 24 buckets for aligned 24h windows, partial-end bucket behavior |
| `test_streak_route.py` | Delegates to GitHub GraphQL helper, canonical login applied |
| `test_overview_totals.py` | `total_commits` sourced from GitHub contributions, not ClickHouse |
| `test_distinct_stats_queries.py` | All endpoints use `uniqExact(sha)`, no aggregate-table queries |
| `test_ingestion_dedupe.py` | Fetch dedupes SHAs, stops at `last_synced_sha`, activity-range dedupes |
| `test_flow_boundary.py` | `process_repo` passes `last_synced_sha` to `fetch_commits` |

---

## Architecture

```
GitHub API ──► Prefect Flow ──► ClickHouse ──► FastAPI ──► Client
                  │                                  │
               sync_state                        X-API-Key
              (per repo SHA)                    + rate limit
```

- **Ingestion**: `vigil_sync()` indexes all repos, then maps `process_repo` per
  repo via Prefect. Each repo task fetches commits since last sync, dedupes
  against stored SHAs, inserts into ClickHouse.
- **Deduplication**: Three layers — `fetch_commits` stops at `last_synced_sha`
  and dedupes within response; `insert_commits` dedupes `(repo, sha)` in batch;
  `process_repo` filters against existing SHAs.
- **Stats**: All `uniqExact(sha)` queries on the raw `commits` table — no
  aggregate tables queried by the API (except `author_commit_days` for streak
  fallback). Overview `total_commits` and streaks come from GitHub GraphQL.
- **Aliasing**: `AUTHOR_LOGIN_CANONICAL_MAP` is injected as a ClickHouse
  `multiIf` expression so all queries transparently map old logins to the
  canonical one.

---

## Documentation

- [API routes](app/api/routes.py) — all 20+ endpoints with Pydantic schemas
- [Configuration](app/core/config.py) — env vars, login map, timezone
- [Flow tasks](app/flow/tasks.py) — fetch, insert, sync state
- [GitHub contributions](app/services/github_contributions.py) — GraphQL streak/calendar helpers
- [ClickHouse migrations](migrations/clickhouse/) — schema-as-code via dbwarden
