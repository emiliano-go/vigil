<p align="center">
  <img src="https://raw.githubusercontent.com/emiliano-go/vigil/refs/heads/master/assets/banner.png" alt="vigil"/>
</p>
<p align="center">
  <h1 align="center">vigil</h1>
</p>

<p align="center">
  <strong>Personal GitHub activity tracking, on your own infrastructure.</strong>
</p>

<p align="center">
  <a href="https://github.com/emiliano-go/vigil/actions/workflows/deploy.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/emiliano-go/vigil/deploy.yml?branch=master&style=for-the-badge&logo=github&label=Deploy" alt="Deploy">
  </a>
  <a href="https://ghcr.io/emiliano-go/vigil">
    <img src="https://img.shields.io/badge/GHCR-latest-2496ED?logo=docker&logoColor=white&style=for-the-badge" alt="GHCR">
  </a>
</p>

---

## Setup

Create two files in the same directory:

**docker-compose.yml**

```yaml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24.8
    container_name: vigil-clickhouse
    restart: unless-stopped
    platform: linux/amd64
    env_file: .env
    environment:
      CLICKHOUSE_USER: ${CLICKHOUSE_USER}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
      CLICKHOUSE_DB: ${CLICKHOUSE_DB}
    networks:
      - vigil_internal
    volumes:
      - clickhouse_data:/var/lib/clickhouse

  prefect-server:
    image: prefecthq/prefect:3-latest
    container_name: vigil-prefect
    restart: unless-stopped
    command: ["prefect", "server", "start", "--host", "0.0.0.0"]
    networks:
      - vigil_internal
    volumes:
      - prefect_data:/root/.prefect

  app:
    image: ghcr.io/emiliano-go/vigil:latest
    pull_policy: always
    container_name: vigil-app
    restart: unless-stopped
    env_file: .env
    environment:
      CLICKHOUSE_HOST: clickhouse
      CLICKHOUSE_PORT: 8123
      CLICKHOUSE_NATIVE_PORT: 9000
      PREFECT_API_URL: http://prefect-server:4200/api
      VIGIL_IN_CONTAINER: "1"
      PORT: 8000
    depends_on:
      - clickhouse
      - prefect-server
    networks:
      - vigil_internal

networks:
  vigil_internal:
    name: vigil_internal
    driver: bridge

volumes:
  clickhouse_data:
  prefect_data:
```

**.env**

```
CLICKHOUSE_USER=app
CLICKHOUSE_PASSWORD=change-me
CLICKHOUSE_DB=default
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_NATIVE_PORT=9000
GITHUB_TOKEN=ghp_your_token_here
PREFECT_API_URL=
ROOT_PATH=
API_KEY=change-me
RATE_LIMIT=60/minute
AUTHOR_LOGIN_CANONICAL_MAP={}
CONTRIBUTION_TIMEZONE_NAME=America/Montevideo
```

Start everything:

```bash
docker compose up -d
```

The container image is pulled from `ghcr.io/emiliano-go/vigil:latest` automatically. After startup the app waits for ClickHouse and Prefect, runs schema migrations, backfills derived tables, and starts syncing every 30 minutes.

## Environment

| Variable | Default | Required | Description |
|---|---|---|---|
| `CLICKHOUSE_USER` | `app` | | ClickHouse user |
| `CLICKHOUSE_PASSWORD` | | yes | ClickHouse password |
| `CLICKHOUSE_DB` | `default` | | ClickHouse database |
| `CLICKHOUSE_HOST` | `localhost` | | ClickHouse hostname |
| `CLICKHOUSE_PORT` | `8123` | | ClickHouse HTTP port |
| `CLICKHOUSE_NATIVE_PORT` | `9000` | | ClickHouse native port |
| `GITHUB_TOKEN` | | yes | Personal access token with `repo` scope |
| `PREFECT_API_URL` | | | Prefect server API URL (automatic in Compose) |
| `ROOT_PATH` | | | URL prefix behind a reverse proxy, e.g. `/vigil` |
| `API_KEY` | | yes | Required on all requests via `X-API-Key` header |
| `RATE_LIMIT` | `60/minute` | | Rate limit string for slowapi |
| `AUTHOR_LOGIN_CANONICAL_MAP` | `{}` | | JSON alias map, e.g. `{"old-username":"current-username"}` |
| `CONTRIBUTION_TIMEZONE_NAME` | `America/Montevideo` | | Timezone for hourly/weekly/streak reporting |

## API

All endpoints require `X-API-Key` header.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/` | Service root |
| | |
| **Repos** | | |
| `GET` | `/api/repos?login=` | List tracked repos (filter by owner) |
| `POST` | `/api/repos` | Add repo to tracking, queue sync. Body: `{"full_name":"owner/repo"}` |
| `DELETE` | `/api/repos/{full_name}` | Remove repo from tracking, wipe data |
| `GET` | `/api/repos/{full_name}/sync-state` | Sync state per repo |
| | |
| **Sync** | | |
| `POST` | `/api/flow/run` | Trigger sync on demand |
| | |
| **Commits** | | |
| `GET` | `/api/commits?repo=&author_login=&limit=` | List commits, `limit` max 1000 |
| | |
| **Stats** | | |
| `GET` | `/api/stats/overview` | Total commits (GitHub), repos, authors, busiest day, top repo |
| `GET` | `/api/stats/streak/{author_login}` | Current/longest streak (GitHub GraphQL) |
| `GET` | `/api/stats/daily?repo=` | Daily totals (no repo: GitHub calendar) |
| `GET` | `/api/stats/daily/authors?days=&author_login=` | Daily totals by author |
| `GET` | `/api/stats/weekly?repo=` | Weekly totals |
| `GET` | `/api/stats/monthly?repo=` | Monthly totals |
| `GET` | `/api/stats/yearly?repo=` | Yearly totals |
| `GET` | `/api/stats/hourly?repo=` | Hourly activity per repo |
| `GET` | `/api/stats/hourly/authors?author_login=&repo=` | Hourly activity by author |
| `GET` | `/api/stats/hourly/authors/range?author_login=&since=&until=&repo=` | Hourly buckets `[since, until)` for an author |
| `GET` | `/api/stats/authors?repo=` | Commit counts by repo and author |
| `GET` | `/api/stats/top-repos?limit=&repo=` | Top repos by commit count |
| `GET` | `/api/stats/merge-ratio?repo=` | Merge vs regular commit ratio |
| `GET` | `/api/stats/activity-range?since=&until=&repo=` | Deduped commits in a time window |

## Usage

```bash
# Health
curl -s -H "X-API-Key: your-key" http://localhost:8000/health/ready

# Overview
curl -H "X-API-Key: your-key" http://localhost:8000/api/stats/overview
# {"total_commits":4800,"total_repos":24,"total_authors":3,...}

# Streak
curl -H "X-API-Key: your-key" http://localhost:8000/api/stats/streak/emiliano-go
# {"current_streak":45,"longest_streak":45,"active_days":321}

# Daily stats (from GitHub contribution calendar)
curl -H "X-API-Key: your-key" http://localhost:8000/api/stats/daily

# Daily stats for a specific repo (from ClickHouse)
curl -H "X-API-Key: your-key" "http://localhost:8000/api/stats/daily?repo=owner/repo"

# Hourly breakdown for an author in a time window
curl -H "X-API-Key: your-key" "http://localhost:8000/api/stats/hourly/authors/range?author_login=emiliano-go&since=2026-07-07T00:00:00Z&until=2026-07-08T00:00:00Z"

# Merge ratio
curl -H "X-API-Key: your-key" http://localhost:8000/api/stats/merge-ratio
# {"total":4200,"merge_commits":312,"regular_commits":3888,"merge_ratio":0.074}

# Top repos
curl -H "X-API-Key: your-key" "http://localhost:8000/api/stats/top-repos?limit=5"

# List commits with filters
curl -H "X-API-Key: your-key" "http://localhost:8000/api/commits?repo=owner/repo&limit=50"

# Trigger sync
curl -X POST -H "X-API-Key: your-key" http://localhost:8000/api/flow/run
```

### Health

```
GET /health/ready
GET /health/alive
GET /health/version
```
