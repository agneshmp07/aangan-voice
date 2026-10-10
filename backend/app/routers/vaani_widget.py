"""Browser voice: let a website visitor talk to the same VaniAgent receptionist.

VaniAgent's developer API (https://api.vaniagent.com/openapi.json, read 2026-10-10):
  POST /api/developer/v1/widget/session  {agent_id, origin}  -> {session_token, ws_url, expires_in}
  GET  /api/developer/v1/widget/embed-snippet                -> {html_snippet, instructions}
  PUT  /api/developer/v1/widget/config   {allowed_origins, max_session_minutes, max_daily_sessions}
Auth: header X-API-Key. The key stays on this server; the browser only ever sees a single-use
5-minute session token. Each browser call still ends in the same post-call capture webhook, so the
rules engine, Telegram handoff and dashboard work exactly as for phone calls.

Abuse guard (every session costs call minutes): per-visitor limit per hour + a daily cap here,
on top of VaniAgent's own max_daily_sessions / max_session_minutes / allowed_origins.
"""
import hashlib
import logging
import time
from collections import deque

import httpx
from fastapi import APIRouter, HTTPException, Request

from .. import clock, db
from ..settings import settings

log = logging.getLogger("aangan.widget")
router = APIRouter(prefix="/api/vaani", tags=["browser voice"])

_recent: dict[str, deque] = {}
_snippet_cache: dict = {"at": 0.0, "value": None}


def _headers() -> dict:
    return {"X-API-Key": settings.vaani_api_key or "", "Content-Type": "application/json"}


def _visitor(request: Request) -> str:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    return hashlib.sha256(ip.encode()).hexdigest()[:16]  # never store raw IPs


def _rate_ok(visitor: str) -> bool:
    now = time.time()
    q = _recent.setdefault(visitor, deque())
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= settings.widget_sessions_per_visitor_hour:
        return False
    q.append(now)
    return True


def _daily_ok() -> bool:
    today = clock.now().date().isoformat()
    n = db.row("SELECT COUNT(*) AS n FROM events WHERE type='widget_session' AND ts>=?", today)["n"]
    return n < settings.widget_max_daily_sessions


@router.get("/status")
def status():
    """Lets the page decide whether to show the 'talk now' button."""
    return {"enabled": bool(settings.vaani_api_key and settings.vaani_agent_id),
            "max_minutes": settings.widget_max_session_minutes}


@router.post("/session")
def create_session(request: Request):
    if not (settings.vaani_api_key and settings.vaani_agent_id):
        raise HTTPException(503, "Browser calling isn't switched on yet.")
    origin = request.headers.get("origin") or settings.public_base_url
    visitor = _visitor(request)
    if not _rate_ok(visitor):
        raise HTTPException(429, "You've started a few calls already. Please try again in a while, or ring the studio.")
    if not _daily_ok():
        raise HTTPException(429, "Today's online calls are used up. Please ring the studio instead.")
    try:
        r = httpx.post(f"{settings.vaani_api_base.rstrip('/')}/widget/session", headers=_headers(), timeout=8,
                       json={"agent_id": settings.vaani_agent_id, "origin": origin, "force_audio": True})
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as e:
        log.warning("widget session refused: %s %s", e.response.status_code, e.response.text[:200])
        raise HTTPException(502, "The receptionist line is busy right now. Please try again or ring the studio.")
    except Exception as e:  # noqa: BLE001
        log.warning("widget session failed: %s", e)
        raise HTTPException(502, "The receptionist line is busy right now. Please try again or ring the studio.")
    db.insert("events", {"ts": clock.iso(clock.now()), "type": "widget_session", "data": visitor})
    return {k: data.get(k) for k in ("session_token", "ws_url", "expires_in")}


@router.get("/embed")
def embed_snippet():
    """VaniAgent's official embed snippet, cached for 10 minutes (it is meant to be public)."""
    if not settings.vaani_api_key:
        raise HTTPException(503, "Browser calling isn't switched on yet.")
    if _snippet_cache["value"] and time.time() - _snippet_cache["at"] < 600:
        return _snippet_cache["value"]
    try:
        r = httpx.get(f"{settings.vaani_api_base.rstrip('/')}/widget/embed-snippet", headers=_headers(), timeout=8)
        r.raise_for_status()
        val = {"html_snippet": r.json().get("html_snippet"), "instructions": r.json().get("instructions")}
    except Exception as e:  # noqa: BLE001
        log.warning("embed snippet failed: %s", e)
        raise HTTPException(502, "Couldn't load the voice widget.")
    _snippet_cache.update(at=time.time(), value=val)
    return val
