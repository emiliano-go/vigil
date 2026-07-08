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

```bash
git clone https://github.com/emiliano-go/vigil.git
cd vigil

# Only edit this file: set your GitHub token and API key
cp .env.example .env

# Start everything
docker compose up -d
```

No code changes. No rebuilds. The container image is pulled from
`ghcr.io/emiliano-go/vigil:latest` automatically.

After startup the app:
1. Waits for ClickHouse and Prefect to be healthy
2. Runs schema migrations via `dbwarden`
3. Backfills the `author_commit_days` table
4. Starts the FastAPI server and begins syncing every 30 minutes

```bash
# Check health
curl -s -H "X-API-Key: your-key" http://localhost:8000/health/ready

# Trigger a sync on demand
curl -X POST -H "X-API-Key: your-key" http://localhost:8000/api/flow/run

# Start querying
curl -H "X-API-Key: your-key" http://localhost:8000/api/stats/overview
```

---

## Environment

All configuration is through environment variables in `.env`. Set them once
and you are done.

| Variable | Default | Required | Description |
|---|---|---|---|
| `CLICKHOUSE_USER` | `app` | | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | (none) | yes | ClickHouse password |
| `CLICKHOUSE_DB` | `default` | | ClickHouse database |
| `CLICKHOUSE_HOST` | `localhost` | | ClickHouse hostname |
| `CLICKHOUSE_PORT` | `8123` | | ClickHouse HTTP port |
| `CLICKHOUSE_NATIVE_PORT` | `9000` | | ClickHouse native port |
| `GITHUB_TOKEN` | (none) | yes | Personal access token with `repo` scope |
| `PREFECT_API_URL` | (none) | | Prefect server API URL (automatic in Compose) |
| `ROOT_PATH` | (none) | | URL prefix when behind a reverse proxy, e.g. `/vigil` |
| `API_KEY` | (none) | yes | Required on all requests via `X-API-Key` header |
| `RATE_LIMIT` | `60/minute` | | Rate limit string for slowapi |
| `AUTHOR_LOGIN_CANONICAL_MAP` | `{}` | | JSON alias map, e.g. `{"old-username":"current-username"}` |
| `CONTRIBUTION_TIMEZONE_NAME` | `America/Montevideo` | | Timezone for hourly/weekly/streak reporting |

---

## API contract

All endpoints require the `X-API-Key` header and count against the rate limit.

### Overview

```
GET /api/stats/overview
```

```json
{
  "total_commits": 4800,
  "total_repos": 24,
  "total_authors": 3,
  "busiest_day": {"period": "2026-03-15", "total": 47},
  "most_active_repo": {"repo": "emiliano-go/vigil", "total": 1200}
}
```

`total_commits` comes from GitHub contribution calendar (all-time, all repos).
Everything else from ClickHouse.

### Streak

```
GET /api/stats/streak/{author_login}
```

```json
{
  "author_login": "emiliano-go",
  "current_streak": 45,
  "longest_streak": 45,
  "last_active_day": "2026-07-08",
  "active_days": 321
}
```

Source of truth is GitHub GraphQL contribution calendar.

### Repos

```
GET /api/repos
```

```json
[
  {
    "full_name": "emiliano-go/vigil",
    "name": "vigil",
    "owner": "emiliano-go",
    "is_org": false,
    "private": false,
    "default_branch": "master"
  }
]
```

### Commits

```
GET /api/commits?repo=&author_login=&limit=100
```

All optional. `limit` defaults to 100, max 1000.

```json
[
  {
    "repo": "emiliano-go/vigil",
    "sha": "abc123",
    "author_login": "emiliano-go",
    "author_name": "Emiliano Gandini Outeda",
    "author_email": "emiliano.gandini@protonmail.com",
    "message": "fix: handle edge case",
    "is_merge": false,
    "committed_at": "2026-07-08T14:30:00"
  }
]
```

### Daily stats

```
GET /api/stats/daily?repo=
```

Without `repo`: totals come from GitHub GraphQL contribution calendar (no `by_repo`).
With `repo`: totals from ClickHouse with `by_repo` breakdown.

```json
{
  "total": [
    {"period": "2026-07-08", "total": 8}
  ],
  "by_repo": [
    {"period": "2026-07-08", "repo": "emiliano-go/vigil", "total": 5}
  ]
}
```

```
GET /api/stats/daily/{repo_full_name}
```

Shorthand for `?repo=`.

### Daily author stats

```
GET /api/stats/daily/authors?days=7&author_login=
```

```json
{
  "total": [{"period": "2026-07-08", "total": 8}],
  "by_author": [{"period": "2026-07-08", "author_login": "emiliano-go", "total": 8}]
}
```

### Monthly / weekly / yearly

```
GET /api/stats/monthly?repo=
GET /api/stats/monthly/{repo_full_name}
GET /api/stats/weekly?repo=
GET /api/stats/yearly?repo=
```

```json
{
  "total": [
    {"period": "2026-07-01", "total": 128}
  ],
  "by_repo": [
    {"period": "2026-07-01", "repo": "emiliano-go/vigil", "total": 40}
  ]
}
```

### Hourly

```
GET /api/stats/hourly?repo=
GET /api/stats/hourly/{repo_full_name}
```

```json
[
  {"repo": "emiliano-go/vigil", "hour": 14, "total": 12}
]
```

### Hourly by author

```
GET /api/stats/hourly/authors?author_login=...&repo=
```

Same shape as `/hourly`, filtered by author login.

### Hourly range (per author)

```
GET /api/stats/hourly/authors/range?author_login=...&since=...&until=...&repo=
```

`sinc e` and `until` are ISO 8601. `[since, until)` semantics: aligned 24h
windows return exactly 24 buckets. Partial-end buckets are included.

```json
[
  {"period": "2026-07-07T00:00:00Z", "total": 0},
  {"period": "2026-07-07T01:00:00Z", "total": 2}
]
```

### Top repos

```
GET /api/stats/top-repos?limit=10&repo=
```

```json
[
  {"repo": "emiliano-go/vigil", "total": 1200}
]
```

### Merge ratio

```
GET /api/stats/merge-ratio?repo=
```

```json
{
  "repo": null,
  "total": 4200,
  "merge_commits": 312,
  "regular_commits": 3888,
  "merge_ratio": 0.074
}
```

### Activity range

```
GET /api/stats/activity-range?sinc e=...&until=...&repo=
```

Returns deduped commits (by `repo` + `sha`) in the time window.

```json
[
  {
    "repo": "emiliano-go/vigil",
    "sha": "abc123",
    "author_login": "emiliano-go",
    "committed_at": "2026-07-08T14:30:00"
  }
]
```

### Authors

```
GET /api/stats/authors?repo=
GET /api/stats/authors/{repo_full_name}
```

```json
[
  {"repo": "emiliano-go/vigil", "author_login": "emiliano-go", "total": 843}
]
```

### Sync state (per repo)

```
GET /api/repos/{repo_full_name}/sync-state
```

```json
{
  "repo": "emiliano-go/vigil",
  "last_synced_sha": "abc123",
  "last_synced_at": "2026-07-08T14:30:00",
  "last_run_status": "success",
  "last_run_at": "2026-07-08T14:30:00"
}
```

### Trigger sync

```
POST /api/flow/run
```

```json
{
  "status": "queued",
  "detail": "Prefect flow queued"
}
```

---

## Running in production

### With Traefik

The `docker-compose.yml` does not publish any host ports. All services are on
the `vigil_internal` bridge network. Point Traefik at the `app` service (port
8000) and set `ROOT_PATH` if the service is behind a path prefix:

```bash
ROOT_PATH=/vigil
```

### Standalone

```bash
export GITHUB_TOKEN=ghp_...
export API_KEY=secret
export CLICKHOUSE_PASSWORD=...
docker run -d --name clickhouse clickhouse/clickhouse-server:24.8
docker run -d --name prefect prefecthq/prefect:3-latest prefect server start --host 0.0.0.0
docker run -d --name vigil \
  --env-file .env \
  ghcr.io/emiliano-go/vigil:latest
```

### Health checks

```
GET /health/ready
GET /health/alive
GET /health/version
```

All require `X-API-Key`.

---

## Data sources

| Field | Source | Why |
|---|---|---|
| `total_commits` in overview | GitHub GraphQL contribution calendar | Matches GitHub profile badge; survives username renames |
| Streak (`current_streak`, `longest_streak`) | GitHub GraphQL contribution calendar | Missing days from old usernames not backfillable via commits API |
| All other stats (daily, hourly, monthly, ...) | ClickHouse `uniqExact(sha)` | Branch duplicates removed; sub-second query times |
| Commit rows | ClickHouse `commits` table | Deduped at fetch, insert, and sync-boundary; all branches included |

Author aliasing via `AUTHOR_LOGIN_CANONICAL_MAP` is transparent at the SQL
level: queries inject a `multiIf` expression so old logins are mapped to the
canonical one without any code changes or data rewrites.

---

## Comparison: GitHub vs vigil

| What | GitHub gives you | vigil gives you |
|---|---|---|
| Commit history | Web UI, REST with pagination | Full table in ClickHouse |
| Multi-branch commits | Only default branch | All branches, deduped by SHA |
| User rename | Breaks history | `AUTHOR_LOGIN_CANONICAL_MAP` |
| Contribution streak | GraphQL only | GraphQL + derived table |
| Hourly breakdown | Not available | `uniqExact(sha)` per hour |
| Merge ratio | Manual counting | `/api/stats/merge-ratio` |
| Sync cadence | Manual fetch | Every 30 min, Prefect orchestrated |
| All stats in one call | No single endpoint | `GET /api/stats/overview` |

---

## What you do not need to do

- Fork, patch, or rebuild the container image. Everything comes from GHCR.
- Hand-edit database schemas. Migrations run automatically on startup.
- Rotate API keys in the code. Set `API_KEY` in `.env`.
- Handle username renames in queries. Set `AUTHOR_LOGIN_CANONICAL_MAP` once.
- Worry about duplicate commits. Dedup happens at every layer.
- Set up cron. The 30-minute sync loop is built into the app process.
