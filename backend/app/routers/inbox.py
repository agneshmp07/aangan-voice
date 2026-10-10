"""Designer inbox: every inbound call with everything the receptionist captured, for the team.

Private: needs the studio key (TOOL_SECRET) as ?key= or X-Aangan-Secret. The page itself is
dashboard/inbox.html; it asks for the key once and keeps it in that browser.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import clock, db
from ..services import leads
from ..settings import settings
from .auth import require_secret

router = APIRouter(prefix="/api/inbox", tags=["designer inbox"], dependencies=[Depends(require_secret)])

FACT_LABELS = [
    ("project_category", "Project"), ("scope", "Scope"), ("bhk", "BHK"), ("carpet_area_sqft", "Carpet area (sq ft)"),
    ("rooms_in_scope", "Rooms"), ("locality", "Locality"), ("city", "City"), ("deadline_text", "Finish by"),
    ("deadline_date", "Finish date"), ("start_text", "Start"), ("site_status", "Site"), ("budget_max_inr", "Budget (volunteered)"),
    ("is_decision_maker", "Decision maker"), ("decision_maker_will_attend", "Decision maker attends"),
    ("referred_by", "Referred by"), ("existing_client", "Existing client"), ("extra_notes", "Notes"),
]


def _call_for(lead: dict) -> dict | None:
    """The call that carries the summary/transcript. Vaani tool leads (vref-...) are linked to the
    Vaani room by a lead_linked event; otherwise fall back to the same number within 2 hours."""
    c = db.row("SELECT * FROM calls WHERE id=?", lead["call_id"])
    if c and c.get("summary"):
        return c
    ev = db.row("SELECT call_id FROM events WHERE type='lead_linked' AND data=? ORDER BY id DESC LIMIT 1", lead["call_id"])
    if ev:
        linked = db.row("SELECT * FROM calls WHERE id=?", ev["call_id"])
        if linked:
            return linked
    if lead.get("phone") and lead.get("created_at"):
        t = clock.parse(lead["created_at"])
        lo, hi = clock.iso(t - timedelta(hours=2)), clock.iso(t + timedelta(hours=2))
        near = db.row("SELECT * FROM calls WHERE phone=? AND created_at BETWEEN ? AND ? AND summary IS NOT NULL "
                      "ORDER BY created_at DESC LIMIT 1", lead["phone"], lo, hi)
        if near:
            return near
    return c


def _status(lead: dict | None, booking: dict | None) -> str:
    if not lead:
        return "dropped"
    if lead.get("stage") in ("won", "lost"):
        return lead["stage"]
    if booking or lead.get("stage") == "booked":
        return "booked"
    if lead.get("verified_client") or (db.unj(lead["facts"], {}).get("existing_client")):
        return "client"
    return {"QUALIFIED": "qualified", "NURTURE": "nurture", "DECLINE": "declined",
            "ESCALATE": "client", "ASK": "incomplete"}.get(lead.get("outcome") or "", "incomplete")


def _item(lead: dict | None, call: dict | None) -> dict:
    f = db.unj(lead["facts"], {}) if lead else {}
    booking = db.row("SELECT * FROM bookings WHERE id=?", lead["booking_id"]) if lead and lead.get("booking_id") else None
    when = (call or {}).get("started_at") or (lead or {}).get("created_at") or (call or {}).get("created_at")
    return {
        "id": lead["id"] if lead else None,
        "call_id": (call or {}).get("id") or (lead or {}).get("call_id"),
        "when": when,
        "name": f.get("caller_name"),
        "phone": (lead or {}).get("phone") or (call or {}).get("phone"),
        "place": ", ".join(p for p in (f.get("locality"), f.get("city")) if p) or None,
        "project": " · ".join(str(p) for p in (f.get("project_category"), f.get("scope"),
                                               f"{f['bhk']} BHK" if f.get("bhk") else None) if p) or None,
        "status": _status(lead, booking),
        "outcome": (lead or {}).get("outcome"),
        "reasons": db.unj(lead["reasons"], []) if lead else [],
        "notes": db.unj(lead["notes"], []) if lead else [],
        "facts": [{"label": lab, "value": f[k]} for k, lab in FACT_LABELS if f.get(k) not in (None, "", [])],
        "asked_price": bool((lead or {}).get("asked_price")),
        "priority": bool((lead or {}).get("priority")),
        "booking": {"start": booking["slot_start"], "status": booking["status"]} if booking else None,
        "claimed_by": (lead or {}).get("claimed_by"),
        "stage": (lead or {}).get("stage"),
        "summary": (call or {}).get("summary"),
        "transcript": None if (call or {}).get("purged") else (call or {}).get("transcript"),
        "recording_url": None if (call or {}).get("purged") else (call or {}).get("recording_url"),
        "duration_s": (call or {}).get("duration_s"),
        "whatsapp": leads.whatsapp_link(lead) if lead and lead.get("phone") else None,
    }


@router.get("")
def inbox(limit: int = 200):
    items, seen_calls = [], set()
    for lead in db.rows("SELECT * FROM leads ORDER BY id DESC LIMIT ?", limit):
        call = _call_for(lead)
        if call:
            seen_calls.add(call["id"])
        seen_calls.add(lead["call_id"])
        items.append(_item(lead, call))
    # Calls where nothing was captured (hung up at the greeting, silent line): still worth a look.
    for call in db.rows("SELECT * FROM calls WHERE synthetic=0 OR synthetic IS NULL ORDER BY created_at DESC LIMIT ?", limit):
        if call["id"] in seen_calls or call["id"].startswith("vref-") or (call.get("ended_reason") == "web" and not call.get("summary")):
            continue
        if call.get("summary") or call.get("phone"):
            items.append(_item(None, call))
    items.sort(key=lambda i: i["when"] or "", reverse=True)
    return {"designers": settings.designers, "items": items[:limit]}


class Who(BaseModel):
    who: str


class Stage(Who):
    stage: str


@router.post("/{lead_id}/claim")
def claim(lead_id: int, body: Who):
    who = body.who.strip()[:60]
    if not who:
        raise HTTPException(400, "Pick your name first.")
    won, owner = leads.claim(lead_id, who)
    return {"ok": won, "claimed_by": owner,
            "message": "It's yours." if won else f"Already taken by {owner}."}


@router.post("/{lead_id}/stage")
def stage(lead_id: int, body: Stage):
    lead = leads.by_id(lead_id)
    if lead and lead.get("claimed_by") and lead["claimed_by"] != body.who.strip():
        return {"ok": False, "message": f"Only {lead['claimed_by']} can update this lead."}
    ok, msg = leads.set_stage(lead_id, body.stage, body.who.strip()[:60])
    return {"ok": ok, "message": msg}
