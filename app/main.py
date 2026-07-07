import asyncio
from contextlib import asynccontextmanager
import logging
from contextlib import suppress

from fastapi import Depends, FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from dbwarden.fastapi import DBWardenHealthRouter, DBWardenRouter, dbwarden_lifespan

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.security import enforce_rate_limit, rate_limit_key, require_api_key
from app.flow.flow import vigil_sync


logger = logging.getLogger("vigil")
SYNC_INTERVAL_SECONDS = 30 * 60


async def _scheduled_vigil_sync() -> None:
    while True:
        try:
            await asyncio.to_thread(vigil_sync)
        except Exception:
            logger.exception("Scheduled vigil sync failed")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_task = asyncio.create_task(_scheduled_vigil_sync())
    try:
        async with dbwarden_lifespan(app, mode="check"):
            yield
    finally:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


limiter = Limiter(
    key_func=rate_limit_key,
    application_limits=[settings.rate_limit],
    headers_enabled=True,
)

app = FastAPI(title="vigil", root_path=settings.root_path, lifespan=lifespan)
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
