from fastapi import FastAPI

from app.api.entitlements import router as entitlements_router

app = FastAPI(title="Ledger-L5")
app.include_router(entitlements_router)
