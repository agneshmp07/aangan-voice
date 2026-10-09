"""Callback queue.

Rules (all enforced here, not in the prompt):
- Never due between 9pm and 9am: checked when queued AND again at dispatch.
- One pending callback per number: new reasons merge into the pending one.
- Dropped calls: one callback per number per CALLBACK_DEDUPE_HOURS, whatever its status.
- A caller who rings back cancels their pending callbacks (T17).
- A "booking uncertain" callback is cancelled at dispatch if the booking did land.
"""
import logging
from datetime import timedelta

import httpx

from .. import clock, db, faults
from ..settings import settings
from . import notify

log = logging.getLogger("aangan.callbacks")
DROPPED = "dropped_call"


def queue(phone: str | None, reason: str, call_id: str | None = None, priority: bool = False,
          note: str | None = None, delay_min: int | None = None) -> dict | None:
    if not phone:
        db.insert("events", {"ts": clock.iso(clock.now()), "type": "callback_no_number", "call_id": call_id,
                             "data": reason})
        return None
    now = clock.now()
    pending = db.row("SELECT * FROM callbacks WHERE phone=? AND status='pending' ORDER BY id LIMIT 1", phone)
    if pending:
        reasons = sorted(set((pending["reason"] or "").split(",")) | {reason})
        db.update("callbacks", pending["id"], {
            "reason": ",".join(r for r in reasons if r), "priority": int(bool(pending["priority"]) or priority),
            "note": "; ".join(x for x in (pending["note"], note) if x)})
        return db.row("SELECT * FROM callbacks WHERE id=?", pending["id"])
    if reason == DROPPED:
        since = clock.iso(now - timedelta(hours=settings.callback_dedupe_hours))
        recent = db.row("SELECT id FROM callbacks WHERE phone=? AND reason LIKE ? AND status!='cancelled' "
                        "AND created_at>=?", phone, f"%{DROPPED}%", since)
        if recent:
            return None
    delay = settings.callback_delay_min if delay_min is None else delay_min
    due = clock.next_allowed_callback(now + timedelta(minutes=0 if priority else delay))
    cid = db.insert("callbacks", dict(phone=phone, call_id=call_id, reason=reason, priority=int(priority),
                                      due_at=clock.iso(due), status="pending", note=note,
                                      created_at=clock.iso(now)))
    return db.row("SELECT * FROM callbacks WHERE id=?", cid)


def cancel_for_phone(phone: str | None, except_call_id: str | None = None) -> int:
    if not phone:
        return 0
    cur = db.execute("UPDATE callbacks SET status='cancelled', note=COALESCE(note,'')||' [caller rang back]' "
                     "WHERE phone=? AND status='pending' AND (call_id IS NULL OR call_id!=?)",
                     phone, except_call_id or "")
    return cur.rowcount


def _dispatch(cb: dict) -> bool:
    faults.check("outbound")
    if settings.callback_mode == "vaani_outbound" and settings.vaani_outbound_url and not settings.mock_mode:
        # Outbound-call API shape unknown [Guessing]: configurable URL, minimal JSON body.
        r = httpx.post(settings.vaani_outbound_url, timeout=5,
                       headers={"Authorization": f"Bearer {settings.vaani_api_key}"} if settings.vaani_api_key else {},
                       json={"to": cb["phone"], "metadata": {"callback_id": cb["id"], "reason": cb["reason"]}})
        r.raise_for_status()
        return True
    lead = db.row("SELECT id, outcome, facts FROM leads WHERE phone=? ORDER BY id DESC LIMIT 1", cb["phone"])
    name = (db.unj(lead["facts"], {}) if lead else {}).get("caller_name") or "caller"
    flag = "🔴 PRIORITY " if cb["priority"] else ""
    text = (f"{flag}📞 <b>Call back {name}</b> on {cb['phone']}\nReason: {cb['reason']}\n"
            f"{('Last outcome: ' + lead['outcome']) if lead and lead['outcome'] else 'No details captured'}\n"
            f"{cb['note'] or ''}")
    plain = text.replace("<b>", "").replace("</b>", "")
    return notify.deliver("head", f"Callback: {cb['phone']}", text, plain, ref=f"callback:{cb['id']}") is not None


def dispatch_due() -> dict:
    now = clock.now()
    stats = {"dispatched": 0, "rescheduled": 0, "cancelled": 0, "failed": 0}
    for cb in db.rows("SELECT * FROM callbacks WHERE status='pending' AND due_at<=? ORDER BY priority DESC, due_at",
                      clock.iso(now)):
        if clock.in_quiet_hours(now):
            db.update("callbacks", cb["id"], {"due_at": clock.iso(clock.next_allowed_callback(now))})
            stats["rescheduled"] += 1
            continue
        if "booking" in (cb["reason"] or ""):
            lead = db.row("SELECT booking_id FROM leads WHERE call_id=?", cb["call_id"])
            if lead and lead["booking_id"]:
                db.update("callbacks", cb["id"], {"status": "cancelled", "note": "booking succeeded after all"})
                stats["cancelled"] += 1
                continue
        try:
            ok = _dispatch(cb)
        except Exception as e:  # noqa: BLE001
            log.warning("callback %s dispatch failed: %s", cb["id"], e)
            ok = False
        if ok:
            db.update("callbacks", cb["id"], {"status": "dispatched", "dispatched_at": clock.iso(now)})
            stats["dispatched"] += 1
        else:
            stats["failed"] += 1  # stays pending; next tick retries
    return stats
