"""End-of-call webhook + Telegram claim webhook + email claim link + cron tick."""
import hashlib
import html
import hmac
import json
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
import httpx

from .. import clock, db, payloads
from ..services import callbacks, leads, notify, sheets
from ..settings import settings
from .auth import require_secret

log = logging.getLogger("aangan.webhooks")
router = APIRouter(tags=["webhooks"])


def record_call(c: dict, raw: dict | None = None) -> tuple[dict, bool]:
    """Upsert a call row. Returns (row, was_already_finalised)."""
    existing = db.row("SELECT * FROM calls WHERE id=?", c["call_id"])
    started = clock.parse(c.get("started_at"))
    ended = clock.parse(c.get("ended_at"))
    duration = c.get("duration_s")
    if duration is None and started and ended:
        duration = (ended - started).total_seconds()
    data = {k: v for k, v in dict(
        phone=c.get("phone"), started_at=clock.iso(started) if started else None,
        ended_at=clock.iso(ended) if ended else clock.iso(clock.now()), duration_s=duration,
        ended_reason=c.get("ended_reason"), language=c.get("language"), transcript=c.get("transcript"),
        summary=c.get("summary"), recording_url=c.get("recording_url"), cost_inr=c.get("cost_inr"),
        cost_source="payload" if c.get("cost_inr") is not None else None, missed=int(bool(c.get("missed"))),
        raw=db.j(raw) if raw is not None else None).items() if v is not None}
    if existing:
        done = bool(existing.get("raw"))
        db.update("calls", c["call_id"], data)
        return db.row("SELECT * FROM calls WHERE id=?", c["call_id"]), done
    if "started_at" not in data:
        data["started_at"] = clock.iso((ended or clock.now()) - timedelta(seconds=duration or 0))
    db.insert("calls", {"id": c["call_id"], "created_at": clock.iso(clock.now()), **data})
    return db.row("SELECT * FROM calls WHERE id=?", c["call_id"]), False


INFO_EVENTS = {"call.started", "transcript.ready", "recording.ready", "transcript.update"}


def _lookup_phone(call_id: str) -> str | None:
    """VaniAgent's documented webhook payload has no caller number. Ask its REST API
    (GET /v1/calls/:id) once, with a short timeout. Field name for the caller is not
    documented for inbound calls [Guessing]: we search the usual names."""
    if settings.mock_mode or not settings.vaani_api_key or call_id.startswith("anon-"):
        return None
    try:
        r = httpx.get(f"{settings.vaani_api_base.rstrip('/')}/calls/{call_id}", timeout=2.0,
                      headers={"X-API-Key": settings.vaani_api_key, "Authorization": f"Bearer {settings.vaani_api_key}"})
        r.raise_for_status()
        return payloads.normalise_phone(payloads._walk(r.json(), ("from_number", "caller_number", "from",
                                                                  "customer_number", "caller", "phone_number")))
    except Exception as e:  # noqa: BLE001
        log.warning("call lookup failed for %s: %s", call_id, e)
        return None


def _find_lead(call_id: str, phone: str | None) -> dict | None:
    """By call id first. If the tools ran under a different id (platform didn't pass the call
    id to tools), link the most recent lead from the same number in the last 2 hours."""
    lead = leads.get(call_id)
    if lead or not phone:
        return lead
    since = clock.iso(clock.now() - timedelta(hours=2))
    return db.row("SELECT * FROM leads WHERE phone=? AND created_at>=? AND call_id!=? ORDER BY id DESC LIMIT 1",
                  phone, since, call_id)


def process_call_end(body: dict) -> dict:
    c = payloads.normalise_call_end(body)
    if not c["call_id"]:
        c["call_id"] = f"anon-{c['phone'] or 'unknown'}-{clock.now():%Y%m%d%H}"
    if c.get("event") in INFO_EVENTS:
        # Not the end of the call: just store what arrived (transcript/recording links).
        if db.row("SELECT id FROM calls WHERE id=?", c["call_id"]):
            upd = {k: c[k] for k in ("transcript", "recording_url", "phone") if c.get(k)}
            if upd:
                db.update("calls", c["call_id"], upd)
        elif c.get("event") == "call.started":
            now = clock.iso(clock.now())
            db.insert("calls", {"id": c["call_id"], "phone": c.get("phone"), "started_at": now, "created_at": now})
        return {"ok": True, "info_event": c["event"]}
    if not c["phone"]:
        c["phone"] = _lookup_phone(c["call_id"])
    call, duplicate = record_call(c, raw=body)
    if duplicate:
        return {"ok": True, "duplicate": True}
    lead = _find_lead(c["call_id"], c["phone"])
    actions = []
    if lead and lead["outcome"] == "QUALIFIED":
        if not lead["booking_id"]:
            # Guardrail: qualified caller hung up before booking → still goes to a designer.
            ch = leads.send_handoff(lead["id"], "qualified_unbooked")
            actions.append(f"handoff_unbooked:{ch}")
        elif not lead["handoff_sent_at"]:
            ch = leads.send_handoff(lead["id"], "booked")
            actions.append(f"handoff_booked:{ch}")
    elif lead is None or lead["outcome"] in (None, "ASK"):
        # Missed, dropped, or cut off mid-qualification → one callback per number, never 9pm–9am.
        cb = callbacks.queue(c["phone"], callbacks.DROPPED, c["call_id"],
                             note="missed call" if c["missed"] else f"ended: {c.get('ended_reason') or 'unknown'}")
        actions.append(f"callback:{cb['due_at'] if cb else 'skipped(dedupe/no number)'}")
    if lead:
        sheets.mirror(lead["id"])
    return {"ok": True, "actions": actions}


def _verify_webhook(raw: bytes, request: Request):
    """Accept VaniAgent's HMAC signature, or our own shared-secret header."""
    sig = request.headers.get("x-vaniagent-signature")
    if settings.vaani_webhook_secret and sig:
        want = hmac.new(settings.vaani_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig.removeprefix("sha256=").strip().lower(), want):
            return
        raise HTTPException(status_code=401, detail="bad signature")
    require_secret(request, request.headers.get("x-aangan-secret"), request.headers.get("authorization"))


@router.post("/webhooks/vaani/call-ended")
@router.post("/webhooks/call-ended")
async def call_ended(request: Request):
    raw = await request.body()
    _verify_webhook(raw, request)
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = {}
    try:
        return process_call_end(body if isinstance(body, dict) else {})
    except Exception as e:  # noqa: BLE001 — never make the platform retry-storm us; log and 200
        log.exception("call-ended processing failed")
        db.insert("events", {"ts": clock.iso(clock.now()), "type": "webhook_failed", "data": str(e)[:300]})
        return {"ok": False, "error": "logged"}


# ---------------------------------------------------------------- Vaani AI webhook
# Vaani (docs.vaanivoice.ai/guides/webhook-setup, read 2026-10-11) POSTs lifecycle events:
#   call_started {event, room_name, phone_number}        call_ended {event, room_name, call_duration (s), end_reason}
#   call_postprocessing {event, call_id, timestamp, data{room_name, call_id, call_duration (ms), end_reason,
#                        summary, entities{...}, dispositions{...}, recording_url, transcript}}
# The caller's number only arrives in call_started, so we keep it on the call row and use it later.
# No signature is documented: authenticate with ?key=TOOL_SECRET on the webhook URL.
VAANI_LOGGED = {"call_ringing", "user_picked_up_at", "human_transfer_initiated", "human_transfer_successful",
                "human_transfer_failed", "call_rejected", "call_no_answer", "call_failed"}


def _link_tool_lead(room: str, phone: str | None, started_at: str | None) -> dict | None:
    """Vaani sends no call id with tool requests (checked on a real call, 2026-10-10), so tool leads are
    keyed by the agent's session_ref ("vref-...") and have no phone. When the call's webhook arrives,
    adopt the phone-less tool lead created during this call and give it the caller's number."""
    if not phone:
        return None
    since = started_at or clock.iso(clock.now() - timedelta(minutes=30))
    lead = db.row("SELECT * FROM leads WHERE phone IS NULL AND (call_id LIKE 'vref-%' OR call_id LIKE 'anon-unknown-%') "
                  "AND created_at>=? ORDER BY created_at ASC LIMIT 1", since)
    if not lead:
        return None
    db.update("leads", lead["id"], {"phone": phone, "updated_at": clock.iso(clock.now())})
    if db.row("SELECT id FROM calls WHERE id=?", lead["call_id"]):
        db.update("calls", lead["call_id"], {"phone": phone})
    db.insert("events", {"ts": clock.iso(clock.now()), "type": "lead_linked", "call_id": room, "data": lead["call_id"]})
    return db.row("SELECT * FROM leads WHERE id=?", lead["id"])


def _seconds(v) -> float:
    """Docs say ms; real payloads (2026-10-10) send seconds (126.17). No call lasts 20,000 s."""
    v = float(v)
    return round(v / 1000, 1) if v > 20000 else round(v, 1)


def process_vaani(body: dict) -> dict:
    event = str(body.get("event") or "").lower()
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    room = str(data.get("room_name") or data.get("call_id") or body.get("room_name") or body.get("call_id") or "") or None
    if not room:
        return {"ok": False, "error": "no room_name/call_id"}
    now = clock.iso(clock.now())
    existing = db.row("SELECT * FROM calls WHERE id=?", room)
    if event == "call_started":
        phone = payloads.normalise_phone(body.get("phone_number") or data.get("phone_number"))
        if existing:
            if phone and not existing.get("phone"):
                db.update("calls", room, {"phone": phone})
        else:
            db.insert("calls", {"id": room, "phone": phone, "started_at": now, "created_at": now})
        return {"ok": True, "event": event}
    if event in VAANI_LOGGED:
        db.insert("events", {"ts": now, "type": f"vaani_{event}", "call_id": room, "data": json.dumps(body)[:900]})
        if event in ("call_rejected", "call_no_answer", "call_failed") and existing and existing.get("phone"):
            callbacks.queue(existing["phone"], callbacks.DROPPED, room, note=event)
        return {"ok": True, "event": event}
    if event == "call_ended":
        dur = body.get("call_duration") or data.get("call_duration")
        upd = {"ended_at": now, "ended_reason": body.get("end_reason") or data.get("end_reason")}
        if dur is not None:
            upd["duration_s"] = _seconds(dur)
        if existing:
            db.update("calls", room, {k: v for k, v in upd.items() if v is not None})
        else:
            db.insert("calls", {"id": room, "started_at": now, "created_at": now, **{k: v for k, v in upd.items() if v is not None}})
        return {"ok": True, "event": event}
    if event == "call_postprocessing":
        phone = (existing or {}).get("phone") or payloads.normalise_phone(data.get("phone_number") or body.get("phone_number"))
        dur_ms = data.get("call_duration")
        upd = {"summary": data.get("summary"), "transcript": data.get("transcript"), "recording_url": data.get("recording_url"),
               "raw": json.dumps(body, ensure_ascii=False)[:20000]}
        if dur_ms is not None:
            upd["duration_s"] = _seconds(dur_ms)
        if not existing:
            db.insert("calls", {"id": room, "phone": phone, "started_at": now, "created_at": now})
        db.update("calls", room, {k: v for k, v in upd.items() if v is not None})
        if not _find_lead(room, phone):
            _link_tool_lead(room, phone, (existing or {}).get("started_at"))
        entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
        if not entities:
            # Nothing extracted (hung up early / silent): treat as dropped, one callback, never 9pm-9am.
            lead = _find_lead(room, phone)
            if not lead or lead.get("outcome") in (None, "ASK"):
                cb = callbacks.queue(phone, callbacks.DROPPED, room, note=data.get("end_reason") or "no details captured")
                return {"ok": True, "event": event, "actions": [f"callback:{cb['due_at'] if cb else 'skipped'}"]}
            return {"ok": True, "event": event, "actions": []}
        out = process_capture({"call_id": room, "phone": phone, "entities": entities,
                               "dispositions": data.get("dispositions")})
        return {"event": event, **out}
    return {"ok": True, "ignored": event or "unknown"}


@router.post("/webhooks/vaani")
async def vaani_webhook(request: Request):
    raw = await request.body()
    _verify_webhook(raw, request)
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = {}
    try:
        return process_vaani(body if isinstance(body, dict) else {})
    except Exception as e:  # noqa: BLE001
        log.exception("vaani webhook failed")
        db.insert("events", {"ts": clock.iso(clock.now()), "type": "webhook_failed", "data": str(e)[:300]})
        return {"ok": False, "error": "logged"}


# ---------------------------------------------------------------- Telegram claim
def _who(user: dict) -> str:
    name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
    return name or user.get("username") or str(user.get("id") or "unknown")


@router.post("/webhooks/telegram")
async def telegram_update(request: Request, x_telegram_bot_api_secret_token: str | None = Header(None)):
    if settings.telegram_webhook_secret and not hmac.compare_digest(
            x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret):
        raise HTTPException(status_code=401)
    upd = await request.json()
    cq = upd.get("callback_query") or {}
    data = cq.get("data") or ""
    user = cq.get("from") or {}
    who, tg_id = _who(user), str(user.get("id") or "") or None
    msg = cq.get("message") or {}
    chat_id, message_id, original = (msg.get("chat") or {}).get("id"), msg.get("message_id"), msg.get("text") or ""
    if data.startswith("claim:"):
        lead_id = int(data.split(":", 1)[1])
        won, owner = leads.claim(lead_id, who, tg_id)
        if won:
            notify.answer_claim(cq.get("id", ""), "It's yours. Call them now, then tap what happened.", chat_id,
                                message_id, html.escape(original) + f"\n\n✅ <b>Claimed by {html.escape(who)}</b>",
                                markup=notify.STAGE_BUTTONS(lead_id))
        else:
            notify.answer_claim(cq.get("id", ""), f"Already taken by {owner}.")
        return {"ok": True, "won": won, "owner": owner}
    if data.startswith("stage:"):
        _, lid, stage = data.split(":", 2)
        ok, label = leads.set_stage(int(lid), stage, who, tg_id)
        if ok:
            keep = notify.STAGE_BUTTONS(int(lid)) if stage == "booked" else None  # won/lost are final
            notify.answer_claim(cq.get("id", ""), f"Marked: {label}", chat_id, message_id,
                                html.escape(original) + f"\n{label} · {html.escape(who)}", markup=keep)
        else:
            notify.answer_claim(cq.get("id", ""), label)
        return {"ok": ok, "stage": stage if ok else None}
    return {"ok": True, "ignored": True}


@router.get("/claim/{lead_id}", response_class=HTMLResponse)
def claim_link(lead_id: int, by: str, t: str):
    """Email fallback: the same first-click-wins claim, via a signed link."""
    if not hmac.compare_digest(t, notify.claim_token(lead_id)):
        raise HTTPException(status_code=403, detail="bad link")
    won, owner = leads.claim(lead_id, by[:60])
    if won:
        st = notify.sign("stage", lead_id)
        links = " · ".join(f"<a href='/stage/{lead_id}?s={s}&by={html.escape(by)}&t={st}'>{label}</a>"
                           for s, label in (("booked", "Consultation booked"), ("won", "Won"), ("lost", "Lost")))
        msg = f"Lead #{lead_id} is yours, {html.escape(by)}. Call them now.<p>Afterwards, mark it: {links}</p>"
    else:
        msg = f"Lead #{lead_id} was already taken by {html.escape(owner or '?')}."
    return f"<!doctype html><meta name=viewport content='width=device-width'><body style='font:18px system-ui;padding:24px'>{msg}</body>"


@router.get("/stage/{lead_id}", response_class=HTMLResponse)
def stage_link(lead_id: int, s: str, by: str, t: str):
    """Email fallback for won/lost reporting (signed link)."""
    if not hmac.compare_digest(t, notify.sign("stage", lead_id)):
        raise HTTPException(status_code=403, detail="bad link")
    ok, label = leads.set_stage(lead_id, s, by[:60])
    return ("<!doctype html><meta name=viewport content='width=device-width'><body style='font:18px system-ui;padding:24px'>"
            f"{'Saved: ' + label if ok else html.escape(label)}</body>")


# ---------------------------------------------------------------- cron
@router.post("/cron/tick", dependencies=[Depends(require_secret)])
def cron_tick():
    from ..services import hubspot
    from .pages import purge_old
    return {"callbacks": callbacks.dispatch_due(), "sweep": leads.sweep(), "purged": purge_old(),
            "hubspot_retried": hubspot.retry_unsynced()}


def weekly_text(m: dict) -> tuple[str, str]:
    """Monday note to Nikhil: last 7 days, in plain words. Never a price quote (costs are his own)."""
    t, c, f, p = m["time_to_claim"], m["cost"], m["funnel"], m.get("pipeline", {})
    med = t["call_to_claim"]["median_min"]
    after = t.get("call_to_claim_after_hours", {}).get("median_min")
    reasons = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in list(m["decline_reasons"].items())[:3]) or "none"
    lines = [
        "<b>Aangan voice desk · last 7 days</b>",
        f"📞 {f['calls']} calls, {m['after_hours']['share_pct'] or 0}% after hours",
        f"✅ {f['qualified']} qualified · {f['claimed']} claimed by a designer",
        f"⏱ Median call → claim: {med if med is not None else '–'} min"
        + (f" (after-hours calls: {after} min)" if after is not None else ""),
        f"🏆 {p.get('won', 0)} won · {p.get('booked', 0)} consultations booked · {p.get('lost', 0)} lost",
        f"🔁 Callbacks done: {m['callbacks'].get('dispatched', 0)} · escalations: {m['escalations']}",
        f"✖ Not a fit: {reasons}",
        (f"💸 System cost Rs {c['total']:,.0f} · Rs {c['per_qualified_lead']:,.0f} per qualified lead"
         if c.get("complete") and c.get("per_qualified_lead") else "💸 Cost: set the per-minute rate to see it"),
    ]
    if t.get("unclaimed"):
        lines.append(f"⚠️ {t['unclaimed']} qualified lead(s) still unclaimed")
    text = "\n".join(lines)
    return text, text.replace("<b>", "").replace("</b>", "")


@router.post("/cron/weekly", dependencies=[Depends(require_secret)])
def cron_weekly():
    from datetime import timedelta
    from .metrics import compute
    end = clock.now()
    m = compute(clock.iso(end - timedelta(days=7)), clock.iso(end))
    html_text, plain = weekly_text(m)
    ch = notify.deliver("head", "[Aangan] Weekly summary", html_text, plain, ref=f"weekly:{end:%Y-%m-%d}")
    return {"ok": bool(ch), "channel": ch}


# ---------------------------------------------------------------- VaniAgent "Data Capture Tool" (Mode B)
# VaniAgent has no mid-call tools. Its post-call "Dispatch Webhook / CRM" action POSTs the fields
# it extracted from the transcript. It allows a URL but no custom headers, so the shared secret
# travels as ?key=. Field names match the rules engine's Facts exactly (agent/vaniagent_fields.md).
# The payload shape is not documented [Guessing]: we search every nesting level for our keys.
from ..rules.engine import Facts as _Facts  # noqa: E402
from dataclasses import fields as _dc_fields  # noqa: E402

FACT_KEYS = {f.name for f in _dc_fields(_Facts)} - {"asked"}
_UNKNOWN = {"", "unknown", "none", "null", "n/a", "na", "not mentioned", "not said", "0"}


def _collect_facts(obj, out: dict, depth=0):
    if depth > 6:
        return
    obj = payloads._maybe_json(obj)
    if isinstance(obj, dict):
        # {"name": "locality", "value": "Baner"} style lists
        if isinstance(obj.get("name"), str) and "value" in obj and obj["name"] in FACT_KEYS:
            out.setdefault(obj["name"], obj["value"])
        for k, v in obj.items():
            if k in FACT_KEYS and not isinstance(v, (dict, list)):
                out.setdefault(k, v)
            else:
                _collect_facts(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _collect_facts(v, out, depth + 1)


def clean_facts(raw: dict) -> dict:
    """Drop 'unknown'/0/empty (= not said; never let a blank become a "no"), then coerce every
    value to the engine's type: "no" must be False, not the truthy string "no"."""
    from dataclasses import asdict
    kept = {k: v for k, v in raw.items() if v is not None and str(v).strip().lower() not in _UNKNOWN}
    typed = asdict(_Facts.from_dict(kept))
    return {k: typed[k] for k in kept if k in typed and typed[k] is not None and k != "asked"} |            {k: v for k, v in kept.items() if k not in typed}


def process_capture(body: dict) -> dict:
    norm = payloads.normalise_tool_call(body)
    call_id = norm["call_id"] or f"anon-{norm['phone'] or 'unknown'}-{clock.now():%Y%m%d%H}"
    phone = norm["phone"] or _lookup_phone(call_id)
    raw: dict = {}
    _collect_facts(body, raw)
    facts = clean_facts(raw)
    wants_human = str(facts.pop("wants_human", "")).lower() in ("yes", "true", "1")
    lead = _find_lead(call_id, phone) or leads.get_or_create(call_id, phone)
    merged = leads.apply_facts(lead, facts)
    d = leads.decide(lead, merged, count_ask=False)
    actions = [f"decision:{d.outcome}"]
    if d.outcome == "ESCALATE":
        cb = callbacks.queue(phone, "escalation", call_id, priority=True, note=merged.get("existing_client_issue"))
        leads.send_handoff(lead["id"], "escalation",
                           extra=f"Callback {'queued for ' + cb['due_at'] if cb else 'NOT queued (no number)'}.")
        actions.append("escalated")
    elif d.outcome == "QUALIFIED":
        # The bot promised a call back: a designer calls to book. Claim button = first tap wins.
        leads.send_handoff(lead["id"], "qualified_unbooked",
                           extra="Qualified by the rules engine after the call. Call back to book the consultation.")
        actions.append("handoff_designers")
    else:
        # ASK (missing facts), NURTURE, DECLINE: the caller was promised a call back, so a person
        # calls. The note carries the engine's reason and the approved line to say, never a price.
        note = f"Engine: {d.outcome} {','.join(d.reasons) or d.ask_field or ''}. Suggested line: {d.say}"
        cb = callbacks.queue(phone, f"post_call:{d.outcome.lower()}", call_id,
                             priority=wants_human or d.priority, note=note)
        actions.append(f"callback:{cb['due_at'] if cb else 'skipped'}")
    sheets.mirror(lead["id"])
    from ..services import hubspot
    if hubspot.enabled():
        actions.append("hubspot:" + ("ok" if "error" not in hubspot.sync_lead(lead["id"]) else "failed"))
    return {"ok": True, "lead_id": lead["id"], "outcome": d.outcome, "actions": actions}


@router.post("/webhooks/vaani/capture")
async def vaani_capture(request: Request):
    _verify_webhook(await request.body(), request)  # ?key=, header, bearer or VaniAgent signature
    try:
        body = json.loads(await request.body() or b"{}")
    except ValueError:
        body = {}
    try:
        return process_capture(body if isinstance(body, dict) else {"data": body})
    except Exception as e:  # noqa: BLE001
        log.exception("capture processing failed")
        db.insert("events", {"ts": clock.iso(clock.now()), "type": "capture_failed", "data": str(e)[:300]})
        return {"ok": False, "error": "logged"}
