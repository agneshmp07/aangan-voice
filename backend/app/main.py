"""Aangan Studio voice receptionist backend.

    uvicorn app.main:app --app-dir backend --reload
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import metrics, tools, webhooks
from .services import callbacks, leads
from .settings import ROOT, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("aangan")
DB_ERROR: str | None = None


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
    global DB_ERROR
    try:
        db.init()
        DB_ERROR = None
    except Exception as e:  # noqa: BLE001 — keep serving: tools still answer with the fallback line
        DB_ERROR = db.redact(f"{type(e).__name__}: {e}")[:300]
        log.error("database init failed: %s", DB_ERROR)
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
    if _dash.exists():
        return RedirectResponse("/dashboard/")
    h = health()
    db_line = "Postgres (persistent)" if h["persistent"] and h["database"] == "postgres" else h["database"]
    return HTMLResponse(
        "<!doctype html><meta name=viewport content='width=device-width'><title>Aangan Voice</title>"
        "<body style='font:16px system-ui;max-width:640px;margin:40px auto;padding:0 16px'>"
        "<h1>Aangan Voice Receptionist</h1><p>Backend is running.</p>"
        f"<ul><li>Database: {db_line}</li><li>Mode: {'mock (no real messages)' if h['mock_mode'] else 'live'}</li>"
        f"{'<li><b>Warning:</b> ' + h['warning'] + '</li>' if h['warning'] else ''}</ul>"
        "<p>Dashboard: coming in the next step. API: <a href='/docs'>/docs</a> · <a href='/health'>/health</a> · "
        "<a href='/api/metrics'>/api/metrics</a></p></body>")


@app.get("/health")
def health():
    persistent = db.is_postgres() or not settings.serverless
    if DB_ERROR:
        return {"ok": False, "mock_mode": settings.mock_mode, "database": "postgres" if db.is_postgres() else "sqlite",
                "persistent": persistent, "warning": "Database unreachable: " + DB_ERROR}
    return {"ok": True, "mock_mode": settings.mock_mode, "database": "postgres" if db.is_postgres() else "sqlite",
            "persistent": persistent,
            "warning": None if persistent else "DATABASE_URL not set: data is lost between requests on Vercel"}
