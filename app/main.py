from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from dbwarden.fastapi import DBWardenHealthRouter, DBWardenRouter, dbwarden_lifespan

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.security import enforce_rate_limit, rate_limit_key, require_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with dbwarden_lifespan(app, mode="check"):
        yield


limiter = Limiter(
    key_func=rate_limit_key,
    application_limits=[settings.rate_limit],
    headers_enabled=True,
)

app = FastAPI(title="vigil", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(api_router)
app.include_router(
    DBWardenHealthRouter(auth_mode="authenticated", api_key=settings.api_key),
    prefix="/health",
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
app.include_router(
    DBWardenRouter(auth_mode="authenticated", api_key=settings.api_key),
    prefix="/db",
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
