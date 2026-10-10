"""Browser voice: a website visitor talks to the same Vaani AI receptionist, in the browser.

Vaani AI (app.vaanivoice.ai) docs, read 2026-10-11 (https://docs.vaanivoice.ai/api-reference/trigger-call):
  POST https://api.vaanivoice.ai/api/trigger-call/   header X-API-Key
  body {"agent_id", "medium": "webrtc", "primary_language", "secondary_language", "voice_gender", "welcome_message"}
  -> {"token", "room_name", "connection_url", "live_captions_url"}   (a LiveKit room)
The browser joins the LiveKit room with that token; the API key never leaves this server.
When the session ends, Vaani sends the same call_postprocessing webhook as for phone calls, so the
rules engine, Telegram/HubSpot handoff and the dashboard treat browser callers exactly like phone callers.

Abuse guard (every session costs call minutes): per-visitor limit per hour + a daily cap.
"""
import hashlib
import logging
import time
from collections import deque

import httpx
from fastapi import APIRouter, HTTPException, Request

from .. import clock, db
from ..settings import settings

log = logging.getLogger("aangan.webvoice")
router = APIRouter(prefix="/api/vaani", tags=["browser voice"])
_recent: dict[str, deque] = {}

WELCOME = "Namaste! You've reached Aangan Studio's AI assistant. This call is recorded. Are you calling about a new project or an existing one?"


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
    n = db.row("SELECT COUNT(*) AS n FROM events WHERE type='web_session' AND ts>=?", today)["n"]
    return n < settings.widget_max_daily_sessions


@router.get("/status")
def status():
    """Lets the page decide whether to show the 'talk now' button."""
    return {"enabled": bool(settings.vaani_api_key and settings.vaani_agent_id),
            "max_minutes": settings.widget_max_session_minutes, "provider": "vaani"}


@router.post("/session")
async def create_session(request: Request):
    if not (settings.vaani_api_key and settings.vaani_agent_id):
        raise HTTPException(503, "Online calling isn't switched on yet.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    lang = "hi" if str(body.get("language", "en")).lower().startswith("hi") else "en"
    visitor = _visitor(request)
    if not _rate_ok(visitor):
        raise HTTPException(429, "You've started a few calls already. Please try again in a while, or ring the studio.")
    if not _daily_ok():
        raise HTTPException(429, "Today's online calls are used up. Please ring the studio instead.")
    payload = {"agent_id": settings.vaani_agent_id, "medium": "webrtc", "primary_language": lang,
               "secondary_language": "hi" if lang == "en" else "en", "voice_gender": "female",
               "welcome_message": WELCOME, "welcome_interruptible": True}
    try:
        r = httpx.post(f"{settings.vaani_api_base.rstrip('/')}/api/trigger-call/", json=payload, timeout=10,
                       headers={"X-API-Key": settings.vaani_api_key, "X-Agent-Id": "aangan-web",
                                "Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        detail = getattr(getattr(e, "response", None), "text", "")[:200]
        log.warning("vaani webrtc session failed: %s %s", e, detail)
        raise HTTPException(502, "The receptionist line is busy right now. Please try again or ring the studio.")
    room = data.get("room_name")
    now = clock.iso(clock.now())
    db.insert("events", {"ts": now, "type": "web_session", "call_id": room, "data": visitor})
    if room and not db.row("SELECT id FROM calls WHERE id=?", room):
        db.insert("calls", {"id": room, "phone": None, "started_at": now, "created_at": now, "ended_reason": "web"})
    return {k: data.get(k) for k in ("token", "connection_url", "room_name", "live_captions_url")}
