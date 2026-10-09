"""Aangan Studio voice receptionist backend.

    uvicorn app.main:app --app-dir backend --reload
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import metrics, tools, webhooks
from .services import callbacks, leads
from .settings import ROOT, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("aangan")


async def _scheduler():
    """In-process cron: every 60s dispatch due callbacks and run the sweeper.
    Production can instead hit POST /cron/tick from any external scheduler."""
    while True:
        try:
            await asyncio.to_thread(callbacks.dispatch_due)
            await asyncio.to_thread(leads.sweep)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    # Serverless (Vercel) freezes between requests: no loop there; an external cron hits /cron/tick.
    run_loop = os.environ.get("RUN_SCHEDULER", "1") == "1" and not settings.serverless
    task = asyncio.create_task(_scheduler()) if run_loop else None
    log.info("Aangan backend up · mock_mode=%s · db=%s", settings.mock_mode, settings.db_path)
    yield
    if task:
        task.cancel()


app = FastAPI(title="Aangan Voice Receptionist", version="1.0", lifespan=lifespan)
app.include_router(tools.router)
app.include_router(webhooks.router)
app.include_router(metrics.router)

_dash = ROOT / "dashboard"
if _dash.exists():
    app.mount("/dashboard", StaticFiles(directory=_dash, html=True), name="dashboard")


@app.get("/")
def root():
    return RedirectResponse("/dashboard/")


@app.get("/health")
def health():
    persistent = db.is_postgres() or not settings.serverless
    return {"ok": True, "mock_mode": settings.mock_mode, "database": "postgres" if db.is_postgres() else "sqlite",
            "persistent": persistent,
            "warning": None if persistent else "DATABASE_URL not set: data is lost between requests on Vercel"}
