"""Server-rendered pages: caller self-booking (/book), and Nikhil's admin (/admin: rules, privacy).

Small, dependency-free HTML in the dashboard's look. Every link is signed (HMAC) or keyed;
nothing here ever shows a price.
"""
import html
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from .. import clock, db
from ..rules import overrides
from ..rules.price_guard import contains_price
from ..services import calendar, leads, notify
from ..settings import settings
from .auth import check_secret

router = APIRouter(tags=["pages"])

CSS = """
:root{color-scheme:light;--bg:#f3ede2;--card:#faf6ef;--ink:#1f1a14;--muted:#6b6053;--line:#e3d9c8;--accent:#b24a22;--ok:#1a7a52}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#14110e;--card:#1c1915;--ink:#f5efe6;--muted:#b3a899;--line:#342e26;--accent:#e07040;--ok:#3cc08a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Instrument Sans",system-ui,sans-serif}
.w{max-width:620px;margin:0 auto;padding:28px 16px 64px}.brand{display:flex;gap:12px;align-items:center;margin-bottom:22px}
.mark{width:40px;height:40px;border-radius:10px;background:var(--accent);display:grid;place-items:center}
.mark i{width:14px;height:14px;border-radius:3px;background:var(--card)}h1{font-size:28px;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em}
.card{background:var(--card);border-radius:18px;padding:20px;margin-top:14px}.muted{color:var(--muted)}
.slots{display:grid;gap:10px;margin-top:14px}.slot{display:block;width:100%;text-align:left;font:inherit;color:var(--ink);background:transparent;
border:1px solid var(--line);border-radius:12px;padding:12px 14px;cursor:pointer}.slot:hover{border-color:var(--accent)}
label{display:block;font-size:14px;color:var(--muted);margin:12px 0 4px}input,textarea{width:100%;font:inherit;padding:10px 12px;border-radius:10px;
border:1px solid var(--line);background:var(--bg);color:var(--ink)}button.go{margin-top:16px;font:inherit;font-weight:600;border:0;border-radius:999px;
padding:10px 18px;background:var(--accent);color:#fff;cursor:pointer}.ok{color:var(--ok);font-weight:600}.err{color:#c0392b;font-weight:600}
.k{font-size:13px;color:var(--muted)}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left}
"""


def shell(title: str, body: str, guard: bool = True) -> HTMLResponse:
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class='w'>"
            f"<div class='brand'><div class='mark'><i></i></div><b>Aangan Studio</b></div>{body}</div></body></html>")
    if guard:
        assert not contains_price(body.replace("<", " <"))  # last line of defence: callers never see a price
    return HTMLResponse(page)


# ---------------------------------------------------------------- caller self-booking
def _lead_for(lead_id: int, t: str) -> dict:
    if not hmac.compare_digest(t or "", notify.sign("book", lead_id)):
        raise HTTPException(403, "This link isn't valid. Please call the studio.")
    lead = leads.by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Not found")
    return lead


@router.get("/book/{lead_id}", response_class=HTMLResponse)
def book_page(lead_id: int, t: str):
    lead = _lead_for(lead_id, t)
    name = html.escape(db.unj(lead["facts"], {}).get("caller_name") or "there")
    if lead.get("booking_id"):
        b = db.row("SELECT slot_start FROM bookings WHERE id=?", lead["booking_id"])
        return shell("You're booked", f"<h1>You're booked, {name}.</h1><p class='muted'>"
                     f"{html.escape(calendar.spoken_label(clock.parse(b['slot_start'])))}. Your designer already has everything "
                     f"you told us on the phone.</p>")
    if not leads.is_qualified_now(lead):
        return shell("Aangan Studio", "<h1>Our team will call you.</h1><p class='muted'>We'd like to talk this through "
                     "with you first. Someone from the studio will ring you on the number you called from.</p>")
    slots = calendar.free_slots(limit=6)
    buttons = "".join(f"<button class='slot' name='slot' value='{s['slot_id']}'>{html.escape(s['label'])}</button>" for s in slots)
    return shell("Book your consultation", f"""
      <h1>Namaste {name}, pick a time.</h1>
      <p class='muted'>A free, no-obligation design consultation with one of our designers. They'll already know
      everything you shared on the call, so you won't need to repeat yourself.</p>
      <div class='card'><form method='post'><input type='hidden' name='t' value='{html.escape(t)}'>
      <div class='slots'>{buttons or "<p class='muted'>No open times this week. We'll call you to fix one.</p>"}</div></form></div>""")


@router.post("/book/{lead_id}", response_class=HTMLResponse)
def book_submit(lead_id: int, t: str = Form(...), slot: str = Form(...)):
    lead = _lead_for(lead_id, t)
    ok, res = leads.book_slot(lead, clock.parse(slot), source="self")
    if not ok:
        msg = {"slot_unavailable": "That time was just taken. Please pick another.",
               "already_booked": "You're already booked.", "not_qualified": "Our team will call you to arrange this."}.get(res, "Something went wrong.")
        return shell("Aangan Studio", f"<h1>{msg}</h1><p><a href='/book/{lead_id}?t={html.escape(t)}'>Back to the times</a></p>")
    label = calendar.spoken_label(clock.parse(slot))
    who = leads.by_id(lead_id).get("claimed_by")
    leads.notify.deliver("designers", f"[Aangan] Self-booked · lead #{lead_id}",
                         f"📅 <b>Caller self-booked</b> lead #{lead_id}: {html.escape(label)}" + (f" · {html.escape(who)}" if who else ""),
                         f"Caller self-booked lead #{lead_id}: {label}", ref=f"lead:{lead_id}:selfbook")
    return shell("You're booked", f"<h1>You're booked.</h1><p class='ok'>{html.escape(label)}</p>"
                 "<p class='muted'>Your designer will see you then. If anything changes, just call the studio.</p>")


# ---------------------------------------------------------------- admin (Nikhil)
def _admin(request: Request) -> str:
    key = request.query_params.get("key") or ""
    if not (settings.tool_secret and check_secret(key)):
        raise HTTPException(401, "Admin key required.")
    return key


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, saved: str | None = None, error: str | None = None):
    key = _admin(request)
    vals = overrides.load(force=True)
    rows = ""
    for k, (_attr, typ, lo, hi, label) in overrides.KNOBS.items():
        cur = vals.get(k, overrides.DEFAULTS[k])
        rows += (f"<label>{html.escape(label)} <span class='k'>(default {overrides.DEFAULTS[k]}, {lo}–{hi})</span></label>"
                 f"<input name='{k}' value='{cur}' inputmode='decimal'>")
    for k, label in overrides.LIST_KNOBS.items():
        rows += f"<label>{html.escape(label)}</label><textarea name='{k}' rows='2'>{html.escape(', '.join(vals.get(k, [])))}</textarea>"
    note = (f"<p class='ok'>Saved. New calls use these rules within a minute.</p>" if saved else "") + \
           (f"<p class='err'>{html.escape(error)}</p>" if error else "")
    return shell("Aangan admin", guard=False, body=f"""
      <h1>Rules</h1><p class='muted'>The receptionist never decides; these rules do. Change them here, no developer needed.
      Every change is logged.</p>{note}
      <div class='card'><form method='post' action='/admin/rules?key={html.escape(key)}'>{rows}
      <button class='go'>Save rules</button></form></div>
      <h1 style='margin-top:34px'>Privacy</h1><p class='muted'>A caller asked us to delete their data (DPDP Act 2023)?
      Enter their number. Calls, leads, callbacks and messages about it are erased. Transcripts and recordings are
      purged automatically after {settings.retention_days} days.</p>
      <div class='card'><form method='post' action='/admin/delete-caller?key={html.escape(key)}'>
      <label>Caller's phone number</label><input name='phone' placeholder='+91 98…' required>
      <button class='go'>Delete this caller's data</button></form></div>""")


@router.post("/admin/rules", response_class=HTMLResponse)
async def admin_rules(request: Request):
    key = _admin(request)
    form = await request.form()
    try:
        clean = {}
        for k in list(overrides.KNOBS) + list(overrides.LIST_KNOBS):
            raw = form.get(k)
            if raw is None or str(raw).strip() == "":
                continue
            v = overrides.validate(k, raw)
            if k in overrides.KNOBS and v == overrides.DEFAULTS[k]:
                continue
            clean[k] = v
    except ValueError as e:
        return admin_home(request, error=str(e))
    now = clock.iso(clock.now())
    db.execute("DELETE FROM rule_overrides")
    for k, v in clean.items():
        db.insert("rule_overrides", {"key": k, "value": json.dumps(v), "updated_at": now, "updated_by": "admin"})
    db.insert("events", {"ts": now, "type": "rules_changed", "data": json.dumps(clean)[:900]})
    overrides.load(force=True)
    return admin_home(request, saved="1")


@router.post("/admin/delete-caller", response_class=HTMLResponse)
async def admin_delete(request: Request):
    key = _admin(request)
    form = await request.form()
    from ..payloads import normalise_phone
    phone = normalise_phone(form.get("phone"))
    if not phone:
        return shell("Aangan admin", "<h1>That doesn't look like a phone number.</h1>")
    n = erase_caller(phone)
    return shell("Aangan admin", f"<h1>Done.</h1><p class='ok'>{n} records about that number were deleted.</p>"
                 f"<p><a href='/admin?key={html.escape(key)}'>Back</a></p>")


def erase_caller(phone: str) -> int:
    ids = [r["id"] for r in db.rows("SELECT id FROM leads WHERE phone=?", phone)]
    calls = [r["id"] for r in db.rows("SELECT id FROM calls WHERE phone=?", phone)]
    n = 0
    for lid in ids:
        n += db.execute("DELETE FROM bookings WHERE lead_id=?", lid).rowcount
        n += db.execute("DELETE FROM sheet_rows WHERE lead_id=?", lid).rowcount
        n += db.execute("DELETE FROM outbox WHERE ref LIKE ?", f"lead:{lid}:%").rowcount
    for cid in calls:
        n += db.execute("DELETE FROM events WHERE call_id=?", cid).rowcount
    n += db.execute("DELETE FROM callbacks WHERE phone=?", phone).rowcount
    n += db.execute("DELETE FROM leads WHERE phone=?", phone).rowcount
    n += db.execute("DELETE FROM calls WHERE phone=?", phone).rowcount
    db.insert("events", {"ts": clock.iso(clock.now()), "type": "caller_erased", "data": f"{n} rows"})
    return n


def purge_old(now: datetime | None = None) -> int:
    """Retention: blank transcripts, recordings and raw payloads older than RETENTION_DAYS."""
    from datetime import timedelta
    cutoff = clock.iso((now or clock.now()) - timedelta(days=settings.retention_days))
    return db.execute("UPDATE calls SET transcript=NULL, summary=NULL, recording_url=NULL, raw=NULL, purged=1 "
                      "WHERE created_at<? AND (purged IS NULL OR purged=0)", cutoff).rowcount
