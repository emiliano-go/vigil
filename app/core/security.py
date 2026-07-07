from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader
from slowapi.errors import RateLimitExceeded

from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(request: Request) -> str:
    return request.headers.get("X-API-Key", "")


def require_api_key(request: Request) -> None:
    expected = settings.api_key.strip()
    provided = get_api_key(request).strip()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key is not configured",
        )

    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "API key"},
        )


def enforce_rate_limit(request: Request) -> None:
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rate limiter is not configured",
        )

    try:
        limiter._check_request_limit(request, None, True)
    except RateLimitExceeded:
        raise

def rate_limit_key(request: Request) -> str:
    api_key = get_api_key(request).strip()
    if api_key:
        return f"api-key:{api_key}"
    client = request.client.host if request.client else "anonymous"
    return f"ip:{client}"
