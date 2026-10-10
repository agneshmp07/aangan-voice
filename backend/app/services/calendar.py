"""Consultation slots and bookings. Mock calendar (SQLite) or Google Calendar.

Slots are offered on working days at settings.slot_hours, never in the past or within
2 hours, and never overlapping an existing booking (mock) or a busy block (Google).
"""
import logging
from datetime import datetime, time, timedelta

from .. import clock, db, faults
from ..settings import settings

log = logging.getLogger("aangan.calendar")

DAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def spoken_label(dt: datetime) -> str:
    dt = dt.astimezone(clock.IST)
    h = dt.hour % 12 or 12
    ampm = "am" if dt.hour < 12 else "pm"
    mins = f":{dt.minute:02d}" if dt.minute else ""
    return f"{DAY[dt.weekday()]} {dt.day} {dt.strftime('%B')} at {h}{mins} {ampm}"


def _candidates(n_days=14):
    start = clock.now() + timedelta(hours=2)
    d = start.date()
    for _ in range(n_days):
        if d.weekday() in settings.working_days:
            for h in settings.slot_hours:
                s = datetime.combine(d, time(h, 0), tzinfo=clock.IST)
                if s >= start:
                    yield s, s + timedelta(minutes=settings.slot_minutes)
        d += timedelta(days=1)


def _busy_mock(lo: datetime, hi: datetime) -> list[tuple[datetime, datetime]]:
    rs = db.rows("SELECT slot_start, slot_end FROM bookings WHERE status='confirmed' AND slot_end>? AND slot_start<?",
                 clock.iso(lo), clock.iso(hi))
    return [(clock.parse(r["slot_start"]), clock.parse(r["slot_end"])) for r in rs]


def google_credentials(scopes: list[str]):
    """Service-account key from GOOGLE_SERVICE_ACCOUNT_JSON (Vercel: paste the file's contents) or a file path."""
    import json as _json
    from google.oauth2 import service_account  # lazy: only needed outside mock mode
    if settings.google_service_account_json:
        return service_account.Credentials.from_service_account_info(_json.loads(settings.google_service_account_json), scopes=scopes)
    return service_account.Credentials.from_service_account_file(settings.google_service_account_file, scopes=scopes)


def google_enabled() -> bool:
    return bool(settings.google_calendar_id and (settings.google_service_account_json or settings.google_service_account_file))


def _google():
    import google_auth_httplib2
    import httplib2
    from googleapiclient.discovery import build
    creds = google_credentials(["https://www.googleapis.com/auth/calendar"])
    # Hard timeout: a slow Google must not hold a call (the guard's deadline is 2.5 s).
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=4))
    return build("calendar", "v3", http=http, cache_discovery=False)


def _busy_google(lo: datetime, hi: datetime):
    svc = _google()
    fb = svc.freebusy().query(body={"timeMin": lo.isoformat(), "timeMax": hi.isoformat(),
                                    "items": [{"id": settings.google_calendar_id}]}).execute()
    busy = fb["calendars"][settings.google_calendar_id]["busy"]
    return [(clock.parse(b["start"]), clock.parse(b["end"])) for b in busy]


def _busy(lo, hi):
    faults.check("calendar")
    if settings.mock_mode or not google_enabled():
        return _busy_mock(lo, hi)
    return _busy_google(lo, hi) + _busy_mock(lo, hi)


def free_slots(limit: int | None = None) -> list[dict]:
    cands = list(_candidates())
    if not cands:
        return []
    busy = _busy(cands[0][0], cands[-1][1])
    out = []
    for s, e in cands:
        if any(bs < e and be > s for bs, be in busy):
            continue
        out.append({"slot_id": clock.iso(s), "start": clock.iso(s), "end": clock.iso(e), "label": spoken_label(s)})
        if len(out) >= (limit or settings.slots_offered):
            break
    return out


def is_free(start: datetime) -> bool:
    return any(clock.parse(s["start"]) == start for s in free_slots(limit=60))


def create_event(start: datetime, summary: str, description: str, lead_id: int | None = None) -> str:
    faults.check("calendar")
    if settings.mock_mode or not google_enabled():
        return f"mock-event-{int(start.timestamp())}"
    ev = _google().events().insert(calendarId=settings.google_calendar_id, body={
        "summary": summary, "description": description, "colorId": "6",
        "location": "Aangan Studio, Pune (or site visit: see notes)",
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60}]},
        "extendedProperties": {"private": {"aangan_lead_id": str(lead_id or "")}},
        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": (start + timedelta(minutes=settings.slot_minutes)).isoformat(), "timeZone": "Asia/Kolkata"},
    }).execute()
    return ev["id"]
