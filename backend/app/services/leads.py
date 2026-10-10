"""Lead state per call, the designer handoff note, and the claim race."""
import csv
import html
import logging
from datetime import timedelta
from pathlib import Path

from .. import clock, db
from ..rules import overrides
from ..rules.engine import Facts, evaluate
from ..settings import ROOT, settings
from . import callbacks, notify, sheets

log = logging.getLogger("aangan.leads")
CARRY_OVER = ("caller_name", "project_category", "scope", "locality", "city", "bhk", "carpet_area_sqft",
              "rooms_in_scope", "deadline_text", "deadline_date", "start_text", "is_decision_maker",
              "authorised_by_decision_maker", "decision_maker_will_attend", "referred_by", "site_status")


def get(call_id: str) -> dict | None:
    return db.row("SELECT * FROM leads WHERE call_id=?", call_id)


def by_id(lead_id: int) -> dict | None:
    return db.row("SELECT * FROM leads WHERE id=?", lead_id)


def get_or_create(call_id: str, phone: str | None) -> dict:
    lead = get(call_id)
    if lead:
        if phone and not lead["phone"]:
            db.update("leads", lead["id"], {"phone": phone})
            lead["phone"] = phone
        return lead
    facts, notes = {}, []
    if phone:
        # Repeat caller (T16): carry what we already know, and flag if we dropped them.
        prev = db.row("SELECT * FROM leads WHERE phone=? AND call_id!=? ORDER BY id DESC LIMIT 1", phone, call_id)
        if prev:
            pf = db.unj(prev["facts"], {})
            facts = {k: pf[k] for k in CARRY_OVER if pf.get(k) not in (None, "")}
            notes.append(f"Repeat caller: earlier call {prev['call_id']} on {prev['created_at'][:10]} "
                         f"(outcome {prev['outcome']}). Facts carried over.")
            if prev["outcome"] in ("QUALIFIED", "ASK", "NURTURE") and not prev["booking_id"] and not prev["claimed_by"]:
                facts["repeat_caller_unanswered"] = True
        callbacks.cancel_for_phone(phone, except_call_id=call_id)
    now = clock.iso(clock.now())
    if not db.row("SELECT id FROM calls WHERE id=?", call_id):
        try:  # stub so volume metrics never depend on the end-of-call webhook arriving
            db.insert("calls", dict(id=call_id, phone=phone, started_at=now, created_at=now))
        except Exception:  # noqa: BLE001
            pass
    try:
        db.insert("leads", dict(call_id=call_id, phone=phone, facts=db.j(facts), asked="{}",
                                notes=db.j(notes), created_at=now, updated_at=now))
    except Exception:  # race: two tools at once on the same call
        pass
    return get(call_id)


def apply_facts(lead: dict, new_facts: dict) -> dict:
    facts = db.unj(lead["facts"], {})
    for k, v in (new_facts or {}).items():
        if v not in (None, "") and k != "asked":
            facts[k] = v
    return facts


def decide(lead: dict, facts: dict, count_ask: bool = True):
    """Run the engine on the stored facts with the SERVER-SIDE ask counts (the LLM's are ignored)."""
    overrides.load()
    asked = db.unj(lead["asked"], {})
    d = evaluate(Facts.from_dict({**facts, "asked": asked}), today=clock.now().date())
    if count_ask and d.outcome == "ASK" and d.ask_field:
        asked[d.ask_field] = asked.get(d.ask_field, 0) + 1
    prior_notes = [n for n in db.unj(lead["notes"], []) if n.startswith("Repeat caller")]
    db.update("leads", lead["id"], dict(
        facts=db.j(facts), asked=db.j(asked), outcome=d.outcome, say_key=d.say_key,
        reasons=db.j(d.reasons), notes=db.j(prior_notes + d.notes), unresolved=db.j(d.unresolved),
        priority=int(d.priority or bool(lead.get("priority"))), asked_price=int(bool(facts.get("asked_price"))),
        updated_at=clock.iso(clock.now())))
    return d


def is_qualified_now(lead: dict) -> bool:
    """Booking gate: re-run the engine; never trust a stored outcome column."""
    overrides.load()
    facts = db.unj(lead["facts"], {})
    d = evaluate(Facts.from_dict({**facts, "asked": db.unj(lead["asked"], {})}), today=clock.now().date())
    return d.outcome == "QUALIFIED"


def verified_client(phone: str | None) -> dict | None:
    path = Path(ROOT / "data" / "clients.csv")
    if not phone or not path.exists():
        return None
    with path.open(encoding="utf8") as fh:
        for r in csv.DictReader(fh):
            if r.get("phone") and r["phone"].replace(" ", "") == phone:
                return r
    return None


# ---------------------------------------------------------------- handoff note
LABELS = [("caller_name", "Name"), ("language", "Language"), ("locality", "Site"), ("project_category", "Type"),
          ("scope", "Scope"), ("bhk", "BHK"), ("carpet_area_sqft", "Carpet area (sq ft)"),
          ("rooms_in_scope", "Rooms in scope"), ("site_status", "Site status"),
          ("deadline_date", "Complete by"), ("deadline_text", "Timeline (their words)"),
          ("start_text", "Start (their words)"), ("budget_max_inr", "Budget they volunteered (INR)"),
          ("referred_by", "Referred by"), ("extra_notes", "Other")]
HEADINGS = {
    "booked": "🟢 New consultation booked",
    "qualified_unbooked": "🟠 Qualified lead, hung up before booking: please call",
    "human_requested": "🟠 Qualified lead asked for a person: please call",
    "escalation": "🔴 URGENT: existing client escalation",
    "reminder": "⏰ Still unclaimed",
}


def handoff_text(lead: dict, kind: str, extra: str | None = None) -> tuple[str, str]:
    f = db.unj(lead["facts"], {})
    lines = [f"<b>{HEADINGS.get(kind, kind)}</b>", f"Lead #{lead['id']} · {lead.get('phone') or 'no number'}"]
    if lead.get("booking_id"):
        b = db.row("SELECT slot_start FROM bookings WHERE id=?", lead["booking_id"])
        if b:
            from .calendar import spoken_label
            lines.append(f"📅 <b>{spoken_label(clock.parse(b['slot_start']))}</b>")
    if extra:
        lines.append(html.escape(extra))
    lines.append("")
    for key, label in LABELS:
        if f.get(key) not in (None, ""):
            lines.append(f"• {label}: {html.escape(str(f[key]))}")
    dm = ("yes" if f.get("is_decision_maker") or f.get("authorised_by_decision_maker")
          else "represented (owners attend)" if f.get("decision_maker_will_attend") else "not confirmed")
    lines.append(f"• Decision-maker: {dm}")
    if f.get("asked_price"):
        lines.append("• Asked about price: yes (deflected, no number given)")
    unresolved = db.unj(lead.get("unresolved"), [])
    if unresolved:
        lines.append(f"• ⚠️ Asked twice, still unclear: {', '.join(unresolved)}")
    notes = db.unj(lead.get("notes"), [])
    if notes:
        lines.append("")
        lines += [f"– {html.escape(n)}" for n in notes]
    call = db.row("SELECT summary, recording_url FROM calls WHERE id=?", lead["call_id"])
    if call and call.get("summary"):
        lines.append(f"\n📝 {html.escape(call['summary'])}")
    if call and call.get("recording_url"):
        lines.append(f"🎧 {html.escape(call['recording_url'])}")
    text = "\n".join(lines)
    plain = text.replace("<b>", "").replace("</b>", "")
    return text, html.unescape(plain)


def send_handoff(lead_id: int, kind: str, extra: str | None = None) -> str | None:
    """Idempotent per lead for designer handoffs; escalations always go out."""
    lead = by_id(lead_id)
    if not lead:
        return None
    if kind != "escalation" and kind != "reminder" and lead.get("handoff_sent_at"):
        return lead.get("handoff_channel")
    audience = "head" if kind == "escalation" else "designers"
    text, plain = handoff_text(lead, kind, extra)
    subject = f"[Aangan] {HEADINGS.get(kind, kind)} · lead #{lead_id}"
    extra_rows = None
    if kind in ("qualified_unbooked", "human_requested") and not lead.get("booking_id"):
        wa = whatsapp_link(lead)
        if wa:
            extra_rows = [[{"text": "📲 Send booking link on WhatsApp", "url": wa}]]
        plain += f"\n\nSelf-booking link for the caller: {booking_link(lead)}"
    channel = notify.deliver(audience, subject, text, plain, ref=f"lead:{lead_id}:{kind}",
                             claim_lead_id=None if kind == "escalation" else lead_id, extra_rows=extra_rows)
    if kind != "reminder":
        db.update("leads", lead_id, {"handoff_sent_at": clock.iso(clock.now()) if channel else None,
                                     "handoff_channel": channel or "failed", "handoff_kind": kind})
    sheets.mirror(lead_id)
    return channel


def claim(lead_id: int, who: str, tg_id: str | None = None) -> tuple[bool, str | None]:
    """First tap wins: a single atomic UPDATE. Returns (won, current_owner)."""
    now = clock.iso(clock.now())
    cur = db.execute("UPDATE leads SET claimed_by=?, claimed_at=?, claimed_by_tg=?, stage='claimed', stage_at=? "
                     "WHERE id=? AND claimed_by IS NULL", who, now, tg_id, now, lead_id)
    owner = db.row("SELECT claimed_by FROM leads WHERE id=?", lead_id)
    won = cur.rowcount == 1
    if won:
        sheets.mirror(lead_id)
    return won, owner["claimed_by"] if owner else None


STAGES = ("booked", "won", "lost")
STAGE_LABEL = {"claimed": "Claimed", "booked": "📅 Consultation booked", "won": "🏆 Won", "lost": "✖ Lost"}


def set_stage(lead_id: int, stage: str, who: str, tg_id: str | None = None) -> tuple[bool, str]:
    """Designer reports what happened after the claim. Only the claimer (by Telegram id, when we
    know it) may update; anyone else gets a polite refusal."""
    if stage not in STAGES:
        return False, "Unknown stage."
    lead = by_id(lead_id)
    if not lead or not lead.get("claimed_by"):
        return False, "Claim the lead first."
    if lead.get("claimed_by_tg") and tg_id and str(tg_id) != str(lead["claimed_by_tg"]):
        return False, f"Only {lead['claimed_by']} can update this lead."
    now = clock.iso(clock.now())
    db.update("leads", lead_id, {"stage": stage, "stage_at": now, "stage_by": who, "updated_at": now})
    sheets.mirror(lead_id)
    return True, STAGE_LABEL[stage]


def booking_link(lead: dict) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/book/{lead['id']}?t={notify.sign('book', lead['id'])}"


def whatsapp_link(lead: dict) -> str | None:
    """wa.me deep link with the message pre-filled: one tap for the designer, no WhatsApp API needed."""
    from urllib.parse import quote
    phone = "".join(ch for ch in (lead.get("phone") or "") if ch.isdigit())
    if len(phone) < 10:
        return None
    name = db.unj(lead.get("facts"), {}).get("caller_name") or "there"
    text = (f"Namaste {name}, this is Aangan Studio. Thank you for calling! You can pick a time for your free design "
            f"consultation here: {booking_link(lead)}")
    return f"https://wa.me/{phone}?text={quote(text)}"


def book_slot(lead: dict, start, source: str) -> tuple[bool, str | int]:
    """Shared by the voice tool and the self-booking page. Re-checks the rules every time."""
    from datetime import timedelta
    from . import calendar
    if not is_qualified_now(lead):
        return False, "not_qualified"
    if lead.get("booking_id"):
        return False, "already_booked"
    if not start or not calendar.is_free(start):
        return False, "slot_unavailable"
    _, plain = handoff_text(lead, "booked")
    f = db.unj(lead["facts"], {})
    event_id = calendar.create_event(start, f"Aangan consultation: {f.get('caller_name') or lead['phone']}", plain)
    bid = db.insert("bookings", dict(lead_id=lead["id"], slot_start=clock.iso(start),
                                     slot_end=clock.iso(start + timedelta(minutes=settings.slot_minutes)),
                                     calendar_event_id=event_id, status="confirmed", created_at=clock.iso(clock.now())))
    upd = {"booking_id": bid, "updated_at": clock.iso(clock.now())}
    if source == "self":
        upd.update(self_booked=1, stage="booked", stage_at=clock.iso(clock.now()), stage_by="caller (self-booked)")
    db.update("leads", lead["id"], upd)
    return True, bid


def sweep(stale_min: int = 15) -> dict:
    """Backstops for anything the webhook or a background task missed."""
    now = clock.now()
    stats = {"handoffs": 0, "reminders": 0}
    cutoff = clock.iso(now - timedelta(minutes=stale_min))
    # Qualified (booked or not) with no successful handoff → send it.
    for lead in db.rows("SELECT id, booking_id FROM leads WHERE outcome='QUALIFIED' AND handoff_sent_at IS NULL "
                        "AND updated_at<=?", cutoff):
        send_handoff(lead["id"], "booked" if lead["booking_id"] else "qualified_unbooked")
        stats["handoffs"] += 1
    # Unclaimed past the claim timeout → re-alert by email to the head (the other channel).
    late = clock.iso(now - timedelta(minutes=settings.claim_timeout_min))
    for lead in db.rows("SELECT * FROM leads WHERE handoff_sent_at IS NOT NULL AND handoff_sent_at<=? AND "
                        "claimed_by IS NULL AND claim_alerted_at IS NULL AND handoff_kind!='escalation'", late):
        text, plain = handoff_text(lead, "reminder", f"Unclaimed for {settings.claim_timeout_min}+ min.")
        notify.send_email(settings.head_email, f"[Aangan] Unclaimed lead #{lead['id']}", plain, f"lead:{lead['id']}:reminder")
        db.update("leads", lead["id"], {"claim_alerted_at": clock.iso(now)})
        stats["reminders"] += 1
    return stats
