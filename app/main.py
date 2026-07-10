from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.entitlements import router as entitlements_router
from app.api.invoices import router as invoices_router
from app.config import settings
from app.services.scheduling import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = start_scheduler() if settings.enable_scheduler else None
    yield
    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title="Ledger-L5", lifespan=lifespan)
app.include_router(entitlements_router)
app.include_router(invoices_router)
