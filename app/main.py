from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.entitlements import router as entitlements_router
from app.api.invoices import router as invoices_router
from app.config import settings
from app.services.scheduling import start_scheduler
from app.web.auth import router as web_auth_router
from app.web.dashboard import router as web_dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = start_scheduler() if settings.enable_scheduler else None
    yield
    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title="Ledger-L5", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret_key)
app.include_router(entitlements_router)
app.include_router(invoices_router)
app.include_router(web_auth_router)
app.include_router(web_dashboard_router)
