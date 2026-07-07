FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY .dbwarden ./.dbwarden

RUN uv sync --frozen

CMD ["uv", "run", "python", "scripts/docker_entrypoint.py"]
