"""The five tools the voice agent can call. All POST, all answer in under 4 seconds."""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from .. import clock, db
from ..guard import META_KEYS, run_tool
from ..rules.lines import say as line
from ..services import calendar, callbacks, leads, sheets
from ..settings import settings
from .auth import require_secret

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_secret)])

NEXT = {"QUALIFIED": ["get_consultation_slots", "book_consultation"], "ASK": ["evaluate_enquiry"],
        "ESCALATE": ["escalate_existing_client"], "NURTURE": ["request_human_callback"], "DECLINE": []}


def _lang(norm, lead=None):
    a = norm["args"] or {}
    if a.get("language"):
        return a["language"]
    if isinstance(a.get("facts"), dict) and a["facts"].get("language"):
        return a["facts"]["language"]
    return db.unj(lead["facts"], {}).get("language") if lead else "en"


def _facts_from(args: dict) -> dict:
    if isinstance(args.get("facts"), dict):
        f = dict(args["facts"])
        if args.get("language") and "language" not in f:
            f["language"] = args["language"]
        return f
    return {k: v for k, v in args.items() if k not in META_KEYS - {"language"}}


def _not_qualified(lead, lang):
    d = leads.decide(lead, db.unj(lead["facts"], {}), count_ask=False)
    return {"ok": False, "error": "not_qualified", "outcome": d.outcome, "say": d.say,
            "next_tools": NEXT.get(d.outcome, [])}


# ---------------------------------------------------------------- evaluate_enquiry
def _evaluate(norm, later):
    lead = leads.get_or_create(norm["_call_id"], norm["phone"])
    facts = leads.apply_facts(lead, _facts_from(norm["args"]))
    d = leads.decide(lead, facts)
    later.append(lambda: sheets.mirror(lead["id"]))
    return {"ok": True, "outcome": d.outcome, "say": d.say, "ask_field": d.ask_field,
            "reasons": d.reasons, "unresolved": d.unresolved, "next_tools": NEXT[d.outcome], "lead_id": lead["id"]}


@router.post("/evaluate_enquiry")
async def evaluate_enquiry(request: Request, background: BackgroundTasks):
    return await run_tool("evaluate_enquiry", request, background, _evaluate)


# ---------------------------------------------------------------- get_consultation_slots
def _slots(norm, later):
    lead = leads.get_or_create(norm["_call_id"], norm["phone"])
    lang = _lang(norm, lead)
    if not leads.is_qualified_now(lead):
        return _not_qualified(lead, lang)
    slots = calendar.free_slots()
    if not slots:
        callbacks.queue(norm["phone"], "no_slots", norm["_call_id"], priority=True)
        return {"ok": False, "error": "no_slots", "slots": [], "say": line("booking.failed", lang)}
    labels = [s["label"] for s in slots]
    joined = ", ".join(labels[:-1]) + (" or " if len(labels) > 1 else "") + labels[-1]
    return {"ok": True, "slots": slots, "say": line("booking.slots", lang, slots=joined),
            "next_tools": ["book_consultation"]}


@router.post("/get_consultation_slots")
async def get_consultation_slots(request: Request, background: BackgroundTasks):
    return await run_tool("get_consultation_slots", request, background, _slots)


# ---------------------------------------------------------------- book_consultation
def _book(norm, later):
    a = norm["args"] or {}
    lead = leads.get_or_create(norm["_call_id"], norm["phone"])
    lang = _lang(norm, lead)
    if not leads.is_qualified_now(lead):  # the gate: code decides, not the model
        return _not_qualified(lead, lang)
    if lead["booking_id"]:
        b = db.row("SELECT slot_start FROM bookings WHERE id=?", lead["booking_id"])
        return {"ok": True, "already_booked": True,
                "say": line("booking.confirmed", lang, slot=calendar.spoken_label(clock.parse(b["slot_start"])))}
    start = clock.parse(a.get("slot_id") or a.get("slot_start") or a.get("start") or a.get("slot"))
    if not start or not calendar.is_free(start):
        slots = calendar.free_slots()
        labels = [s["label"] for s in slots] or ["no open times"]
        return {"ok": False, "error": "slot_unavailable", "slots": slots,
                "say": line("booking.slots", lang, slots=", ".join(labels[:-1]) + (" or " if len(labels) > 1 else "") + labels[-1])}
    _, plain = leads.handoff_text(lead, "booked")
    f = db.unj(lead["facts"], {})
    event_id = calendar.create_event(start, f"Aangan consultation: {f.get('caller_name') or lead['phone']}", plain)
    end = start + timedelta(minutes=settings.slot_minutes)
    bid = db.insert("bookings", dict(lead_id=lead["id"], slot_start=clock.iso(start), slot_end=clock.iso(end),
                                     calendar_event_id=event_id, status="confirmed", created_at=clock.iso(clock.now())))
    db.update("leads", lead["id"], {"booking_id": bid, "updated_at": clock.iso(clock.now())})
    later.append(lambda: leads.send_handoff(lead["id"], "booked"))
    return {"ok": True, "booking_id": bid, "slot": clock.iso(start),
            "say": line("booking.confirmed", lang, slot=calendar.spoken_label(start)), "next_tools": []}


@router.post("/book_consultation")
async def book_consultation(request: Request, background: BackgroundTasks):
    return await run_tool("book_consultation", request, background, _book)


# ---------------------------------------------------------------- escalate_existing_client
def _escalate(norm, later):
    a = norm["args"] or {}
    lead = leads.get_or_create(norm["_call_id"], norm["phone"])
    complaint = a.get("complaint", True)
    issue = a.get("issue") or a.get("summary") or a.get("existing_client_issue") or "Existing client called"
    facts = leads.apply_facts(lead, {"existing_client": True, "complaint": complaint, "existing_client_issue": issue,
                                     "caller_name": a.get("caller_name") or a.get("name"),
                                     "locality": a.get("project_location") or a.get("locality"),
                                     "language": a.get("language"),
                                     "extra_notes": f"Designer named by caller: {a['designer_name']}" if a.get("designer_name") else None})
    d = leads.decide(lead, facts)
    client = leads.verified_client(norm["phone"])
    db.update("leads", lead["id"], {"verified_client": int(bool(client)), "priority": 1})
    verified = (f"Verified client: {client.get('name')} / designer {client.get('designer')}" if client
                else "UNVERIFIED: number not on the client list")
    cb = callbacks.queue(norm["phone"], "escalation", norm["_call_id"], priority=True, note=issue)
    when = f"Callback queued for {cb['due_at']}" if cb else "No caller number: cannot queue callback"
    later.append(lambda: leads.send_handoff(lead["id"], "escalation", extra=f"{verified}. {when}."))
    return {"ok": True, "outcome": d.outcome, "say": d.say, "verified": bool(client), "next_tools": []}


@router.post("/escalate_existing_client")
async def escalate_existing_client(request: Request, background: BackgroundTasks):
    return await run_tool("escalate_existing_client", request, background, _escalate)


# ---------------------------------------------------------------- request_human_callback
def _human(norm, later):
    a = norm["args"] or {}
    lead = leads.get_or_create(norm["_call_id"], norm["phone"])
    lang = _lang(norm, lead)
    reason = str(a.get("reason") or "caller_requested")[:120]
    cb = callbacks.queue(norm["phone"], f"requested:{reason}", norm["_call_id"], priority=bool(a.get("urgent")))
    if lead["outcome"] == "QUALIFIED" and not lead["booking_id"]:
        later.append(lambda: leads.send_handoff(lead["id"], "human_requested", extra=f"Reason: {reason}"))
    if not cb:
        return {"ok": False, "error": "no_number_or_already_queued", "say": line("human.request", lang)}
    due = clock.parse(cb["due_at"])
    morning = due.date() > clock.now().date() or clock.in_quiet_hours(clock.now())
    return {"ok": True, "callback_due": cb["due_at"],
            "say": line("fallback.callback_morning" if morning else "human.request", lang), "next_tools": []}


@router.post("/request_human_callback")
async def request_human_callback(request: Request, background: BackgroundTasks):
    return await run_tool("request_human_callback", request, background, _human)
