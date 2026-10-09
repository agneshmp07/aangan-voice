"""API and failure-mode tests. Everything runs in mock mode against a temp SQLite DB."""
import os
import threading
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import clock, db, settings as settings_mod
from app.faults import FAULTS
from app.rules.lines import LINES
from app.rules.price_guard import contains_price

FALLBACK = LINES["fallback.callback"]["en"]
PHONE = "+919800000001"
QUALIFIED_FACTS = dict(project_category="residential", scope="full_home", locality="Kothrud", bhk=3,
                       carpet_area_sqft=1400, deadline_text="by March", is_decision_maker=True,
                       caller_name="Priya")


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    """TEST_POSTGRES=1 runs every API test against a real local Postgres (pgserver),
    the same engine Supabase runs, instead of SQLite."""
    if os.environ.get("TEST_POSTGRES") != "1":
        return None
    import pgserver
    srv = pgserver.get_server(str(tmp_path_factory.mktemp("pg")), cleanup_mode="stop")
    return srv.get_uri()


@pytest.fixture()
def api(tmp_path, monkeypatch, pg_url):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    if pg_url:
        import psycopg
        with psycopg.connect(pg_url, autocommit=True) as c:
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        monkeypatch.setenv("DATABASE_URL", pg_url)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setenv("RUN_SCHEDULER", "0")
    monkeypatch.setenv("TOOL_TIMEOUT_S", "0.5")
    monkeypatch.delenv("TOOL_SECRET", raising=False)
    settings_mod.reload()
    FAULTS.clear()
    clock.freeze(datetime(2026, 10, 12, 11, 0, tzinfo=clock.IST))  # Monday 11am
    from app.main import app
    with TestClient(app) as c:
        yield c
    FAULTS.clear()
    clock.freeze(None)


def tool(api, name, call_id="call-1", phone=PHONE, **args):
    t0 = time.perf_counter()
    r = api.post(f"/tools/{name}", json={"call_id": call_id, "caller_phone": phone, **args})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 4.0, f"{name} took {elapsed:.2f}s"
    body = r.json()
    assert not contains_price(body.get("say"))
    return body


def qualify(api, call_id="call-1", phone=PHONE):
    return tool(api, "evaluate_enquiry", call_id, phone, facts=QUALIFIED_FACTS)


def outbox(channel=None, status=None):
    q, a = "SELECT * FROM outbox WHERE 1=1", []
    if channel:
        q += " AND channel=?"; a.append(channel)
    if status:
        q += " AND status=?"; a.append(status)
    return db.rows(q, *a)


# ---------------------------------------------------------------- happy path
def test_full_happy_path_books_and_hands_off(api):
    d = qualify(api)
    assert d["outcome"] == "QUALIFIED" and "get_consultation_slots" in d["next_tools"]
    s = tool(api, "get_consultation_slots")
    assert s["ok"] and len(s["slots"]) == 3 and "Monday 12 October at 3 pm" in s["say"]
    b = tool(api, "book_consultation", slot_id=s["slots"][0]["slot_id"])
    assert b["ok"] and b["say"].startswith("You're booked for Monday 12 October at 3 pm")
    sent = outbox("telegram")
    assert len(sent) == 1 and "New consultation booked" in sent[0]["body"] and "Kothrud" in sent[0]["body"]
    assert db.row("SELECT COUNT(*) n FROM sheet_rows")["n"] == 1
    # the booked slot is no longer offered
    s2 = tool(api, "get_consultation_slots", call_id="call-2", phone="+919800000002")
    assert s2["error"] == "not_qualified"  # (new caller, nothing collected yet)


def test_handoff_note_has_everything_already_asked(api):
    tool(api, "evaluate_enquiry", facts={**QUALIFIED_FACTS, "asked_price": True, "referred_by": "Shruti Joshi"})
    s = tool(api, "get_consultation_slots")
    tool(api, "book_consultation", slot_id=s["slots"][0]["slot_id"])
    body = outbox("telegram")[0]["body"]
    for must in ("Priya", "Kothrud", "1400", "by March", "Shruti Joshi", "Asked about price: yes", "Decision-maker: yes"):
        assert must in body, must


# ---------------------------------------------------------------- 4-second rule
@pytest.mark.parametrize("fault", ["slow:3", "error"])
def test_calendar_failure_still_answers_fast_and_queues_callback(api, fault):
    qualify(api)
    FAULTS["calendar"] = fault
    r = tool(api, "get_consultation_slots")
    assert r["ok"] is False and r["say"] == FALLBACK
    cb = db.row("SELECT * FROM callbacks WHERE phone=?", PHONE)
    assert cb and "tool_failed:get_consultation_slots" in cb["reason"]


def test_booking_failure_is_priority_callback_and_cancelled_if_booking_landed(api):
    qualify(api)
    slot = tool(api, "get_consultation_slots")["slots"][0]["slot_id"]
    FAULTS["calendar"] = "error"
    r = tool(api, "book_consultation", slot_id=slot)
    assert r["say"] == FALLBACK
    cb = db.row("SELECT * FROM callbacks WHERE phone=?", PHONE)
    assert cb["reason"] == "booking_uncertain" and cb["priority"] == 1
    # Simulate the slow booking having completed after all → cron cancels the callback
    lead = db.row("SELECT id FROM leads WHERE call_id='call-1'")
    bid = db.insert("bookings", {"lead_id": lead["id"], "slot_start": slot, "status": "confirmed"})
    db.update("leads", lead["id"], {"booking_id": bid})
    api.post("/cron/tick")
    assert db.row("SELECT status FROM callbacks WHERE id=?", cb["id"])["status"] == "cancelled"


def test_engine_crash_still_answers(api, monkeypatch):
    from app.services import leads
    monkeypatch.setattr(leads, "decide", lambda *a, **k: 1 / 0)
    r = tool(api, "evaluate_enquiry", facts=QUALIFIED_FACTS)
    assert r["say"] == FALLBACK and db.row("SELECT * FROM callbacks WHERE phone=?", PHONE)


def test_database_down_still_answers_and_logs_to_file(api, monkeypatch, tmp_path):
    def broken(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(db, "conn", broken)
    r = tool(api, "evaluate_enquiry", facts=QUALIFIED_FACTS)
    assert r["say"] == FALLBACK
    assert "disk full" in (tmp_path / "fallback.log").read_text(encoding="utf8")


def test_garbage_body_still_answers(api):
    r = api.post("/tools/evaluate_enquiry", content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 200 and r.json()["say"]


def test_tool_output_is_price_guarded(api, monkeypatch):
    from app.services import calendar
    monkeypatch.setattr(calendar, "spoken_label", lambda dt: "Monday, about 18 lakh")
    qualify(api)
    r = tool(api, "get_consultation_slots")
    assert r["say"] == FALLBACK


# ---------------------------------------------------------------- booking gate
@pytest.mark.parametrize("facts", [
    {},                                                                  # nothing known → ASK
    {**QUALIFIED_FACTS, "locality": "Nashik"},                           # DECLINE
    {**QUALIFIED_FACTS, "deadline_text": None, "deadline_date": None},   # ASK timeline
])
def test_booking_rejects_unqualified(api, facts):
    tool(api, "evaluate_enquiry", facts=facts)
    slot = "2026-10-12T15:00:00+05:30"
    r = tool(api, "book_consultation", slot_id=slot)
    assert r["ok"] is False and r["error"] == "not_qualified"
    assert db.row("SELECT COUNT(*) n FROM bookings")["n"] == 0


def test_booking_ignores_a_tampered_outcome_column(api):
    tool(api, "evaluate_enquiry", facts={**QUALIFIED_FACTS, "locality": "Mumbai"})
    db.execute("UPDATE leads SET outcome='QUALIFIED'")
    r = tool(api, "book_consultation", slot_id="2026-10-12T15:00:00+05:30")
    assert r["error"] == "not_qualified"


def test_booking_without_any_evaluation_is_rejected(api):
    r = tool(api, "book_consultation", call_id="cold", slot_id="2026-10-12T15:00:00+05:30")
    assert r["error"] == "not_qualified"


def test_double_booking_same_slot_offers_alternatives(api):
    qualify(api, "a", "+919800000011")
    slot = tool(api, "get_consultation_slots", "a", "+919800000011")["slots"][0]["slot_id"]
    tool(api, "book_consultation", "a", "+919800000011", slot_id=slot)
    qualify(api, "b", "+919800000012")
    r = tool(api, "book_consultation", "b", "+919800000012", slot_id=slot)
    assert r["error"] == "slot_unavailable" and slot not in [s["slot_id"] for s in r["slots"]]


# ---------------------------------------------------------------- ask at most twice
def test_backend_counts_asks_even_if_model_lies(api):
    facts = {k: v for k, v in QUALIFIED_FACTS.items() if k != "deadline_text"}
    r1 = tool(api, "evaluate_enquiry", facts={**facts, "asked": {}})
    r2 = tool(api, "evaluate_enquiry", facts={**facts, "asked": {}})
    r3 = tool(api, "evaluate_enquiry", facts={**facts, "asked": {}})
    assert r1["ask_field"] == r2["ask_field"] == "deadline"
    assert r3["outcome"] == "QUALIFIED" and "deadline" in r3["unresolved"]
    slot = tool(api, "get_consultation_slots")["slots"][0]["slot_id"]
    tool(api, "book_consultation", slot_id=slot)
    assert "Asked twice, still unclear: deadline" in outbox("telegram")[0]["body"]


# ---------------------------------------------------------------- hang-ups and dropped calls
def end_call(api, call_id="call-1", phone=PHONE, **kw):
    r = api.post("/webhooks/vaani/call-ended", json={"call_id": call_id, "from_number": phone, **kw})
    assert r.status_code == 200
    return r.json()


def test_qualified_hangup_before_booking_still_reaches_designer(api):
    qualify(api)
    res = end_call(api, duration=140, ended_reason="customer-ended-call")
    assert any(a.startswith("handoff_unbooked") for a in res["actions"])
    msg = outbox("telegram")[0]["body"]
    assert "hung up before booking" in msg and "Kothrud" in msg


def test_qualified_hangup_backstop_without_webhook(api):
    qualify(api)
    clock.freeze(datetime(2026, 10, 12, 11, 30, tzinfo=clock.IST))
    out = api.post("/cron/tick").json()
    assert out["sweep"]["handoffs"] == 1


def test_dropped_call_gets_exactly_one_callback(api):
    tool(api, "evaluate_enquiry", facts={"project_category": "residential"})  # ASK, then line drops
    end_call(api, duration=40, ended_reason="network-error")
    end_call(api, "call-2", duration=10)  # drops again
    end_call(api, "call-3", missed=True, status="no-answer")
    assert db.row("SELECT COUNT(*) n FROM callbacks WHERE phone=?", PHONE)["n"] == 1


def test_missed_call_at_night_is_called_back_after_9am(api):
    clock.freeze(datetime(2026, 9, 9, 22, 47, tzinfo=clock.IST))  # T08
    end_call(api, "t08", "+919800000008", status="no-answer")
    cb = db.row("SELECT * FROM callbacks WHERE phone='+919800000008'")
    assert cb["due_at"] == "2026-09-10T09:00:00+05:30"


def test_early_morning_drop_waits_until_9(api):
    clock.freeze(datetime(2026, 9, 10, 8, 30, tzinfo=clock.IST))
    end_call(api, "x", "+919800000009", duration=20)
    assert db.row("SELECT due_at FROM callbacks")["due_at"] == "2026-09-10T09:00:00+05:30"


def test_cron_never_dispatches_in_quiet_hours(api):
    end_call(api, duration=20)  # due 11:10
    clock.freeze(datetime(2026, 10, 12, 21, 30, tzinfo=clock.IST))
    out = api.post("/cron/tick").json()["callbacks"]
    assert out["dispatched"] == 0 and out["rescheduled"] == 1
    assert db.row("SELECT due_at FROM callbacks")["due_at"] == "2026-10-13T09:00:00+05:30"
    clock.freeze(datetime(2026, 10, 13, 9, 1, tzinfo=clock.IST))
    assert api.post("/cron/tick").json()["callbacks"]["dispatched"] == 1
    assert "Call back" in outbox("telegram")[-1]["body"]


def test_caller_ringing_back_cancels_pending_callback(api):
    # T17: dropped at 1:12, rang back two minutes later
    end_call(api, "t17a", duration=72)
    assert db.row("SELECT status FROM callbacks")["status"] == "pending"
    qualify(api, "t17b")
    assert db.row("SELECT status FROM callbacks")["status"] == "cancelled"


def test_webhook_is_idempotent(api):
    qualify(api)
    end_call(api, duration=100)
    assert end_call(api, duration=100).get("duplicate")
    assert len(outbox("telegram")) == 1


def test_repeat_caller_we_dropped_gets_apology_and_priority(api):
    # T16: first enquiry never followed up
    tool(api, "evaluate_enquiry", "monday", facts={"caller_name": "Girish Nair", "locality": "Viman Nagar", "bhk": 3,
                                                   "project_category": "residential", "scope": "full_home"})
    clock.freeze(datetime(2026, 10, 16, 10, 38, tzinfo=clock.IST))
    r = tool(api, "evaluate_enquiry", "friday", facts={})
    assert r["say"].startswith("I'm so sorry nobody got back to you")
    lead = db.row("SELECT * FROM leads WHERE call_id='friday'")
    assert lead["priority"] == 1 and "Viman Nagar" in lead["facts"]


# ---------------------------------------------------------------- escalation
def test_existing_client_escalation(api, tmp_path, monkeypatch):
    r = tool(api, "escalate_existing_client", caller_name="Sheetal Deshpande",
             issue="Designer Aryan unresponsive for 5 days", designer_name="Aryan", project_location="Viman Nagar")
    assert r["outcome"] == "ESCALATE" and r["verified"] is False
    msg = outbox("telegram")[0]
    assert "URGENT" in msg["body"] and "UNVERIFIED" in msg["body"] and "Aryan" in msg["body"]
    cb = db.row("SELECT * FROM callbacks WHERE phone=?", PHONE)
    assert cb["priority"] == 1 and cb["reason"] == "escalation"


# ---------------------------------------------------------------- Telegram claim race
def tg_tap(api, lead_id, user_id, name):
    return api.post("/webhooks/telegram", json={"callback_query": {
        "id": f"cq{user_id}", "data": f"claim:{lead_id}", "from": {"id": user_id, "first_name": name},
        "message": {"message_id": 1, "chat": {"id": -100}, "text": "lead"}}}).json()


def test_first_tap_wins(api):
    lead_id = qualify(api)["lead_id"]
    a = tg_tap(api, lead_id, 1, "Asha")
    b = tg_tap(api, lead_id, 2, "Rohan")
    assert a["won"] and not b["won"] and b["owner"] == "Asha"


def test_first_tap_wins_under_concurrency(api):
    lead_id = qualify(api)["lead_id"]
    from app.services import leads
    results = []
    barrier = threading.Barrier(8)

    def tap(i):
        barrier.wait()
        results.append(leads.claim(lead_id, f"designer{i}")[0])

    ts = [threading.Thread(target=tap, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count(True) == 1


def test_email_claim_link(api):
    from app.services import notify
    lead_id = qualify(api)["lead_id"]
    assert api.get(f"/claim/{lead_id}?by=Asha&t=wrong").status_code == 403
    ok = api.get(f"/claim/{lead_id}?by=Asha&t={notify.claim_token(lead_id)}")
    assert "is yours" in ok.text
    again = api.get(f"/claim/{lead_id}?by=Rohan&t={notify.claim_token(lead_id)}")
    assert "already taken by Asha" in again.text


# ---------------------------------------------------------------- Telegram → email fallback
def test_telegram_down_falls_back_to_email(api):
    FAULTS["telegram"] = "error"
    qualify(api)
    slot = tool(api, "get_consultation_slots")["slots"][0]["slot_id"]
    tool(api, "book_consultation", slot_id=slot)
    assert outbox("telegram", "failed") and outbox("email", "mock_sent")
    mail = outbox("email")[0]["body"]
    assert "/claim/" in mail and "Kothrud" in mail
    assert db.row("SELECT handoff_channel FROM leads")["handoff_channel"] == "email"


def test_both_channels_down_is_retried_by_cron(api):
    FAULTS["telegram"] = FAULTS["email"] = "error"
    qualify(api)
    slot = tool(api, "get_consultation_slots")["slots"][0]["slot_id"]
    tool(api, "book_consultation", slot_id=slot)
    assert db.row("SELECT handoff_sent_at, handoff_channel FROM leads")["handoff_channel"] == "failed"
    FAULTS.clear()
    clock.freeze(datetime(2026, 10, 12, 11, 30, tzinfo=clock.IST))
    api.post("/cron/tick")
    assert db.row("SELECT handoff_channel FROM leads")["handoff_channel"] == "telegram"


def test_unclaimed_lead_alerts_head_by_email(api):
    qualify(api)
    end_call(api, duration=100)
    clock.freeze(datetime(2026, 10, 12, 11, 45, tzinfo=clock.IST))
    assert api.post("/cron/tick").json()["sweep"]["reminders"] == 1
    assert "Unclaimed lead" in outbox("email")[0]["subject"]


# ---------------------------------------------------------------- human callback
def test_human_callback_at_night_says_tomorrow_morning(api):
    clock.freeze(datetime(2026, 10, 12, 23, 15, tzinfo=clock.IST))
    r = tool(api, "request_human_callback", reason="wants to speak to a person")
    assert "tomorrow morning" in r["say"] and r["callback_due"].startswith("2026-10-13T09:00")


def test_hindi_fallback_line(api, monkeypatch):
    from app.services import leads
    monkeypatch.setattr(leads, "decide", lambda *a, **k: 1 / 0)
    r = tool(api, "evaluate_enquiry", language="hi", facts={})
    assert r["say"] == LINES["fallback.callback"]["hi"]


# ---------------------------------------------------------------- auth
def test_secret_required_when_configured(api, monkeypatch):
    monkeypatch.setenv("TOOL_SECRET", "s3cret")
    settings_mod.reload()
    assert api.post("/tools/evaluate_enquiry", json={}).status_code == 401
    assert api.post("/tools/evaluate_enquiry", json={}, headers={"X-Aangan-Secret": "s3cret"}).status_code == 200
    assert api.post("/tools/evaluate_enquiry", json={}, headers={"Authorization": "Bearer s3cret"}).status_code == 200


# ---------------------------------------------------------------- metrics
def test_metrics(api, monkeypatch):
    qualify(api, "m1", "+919800000101")
    slot = tool(api, "get_consultation_slots", "m1", "+919800000101")["slots"][0]["slot_id"]
    tool(api, "book_consultation", "m1", "+919800000101", slot_id=slot)
    end_call(api, "m1", "+919800000101", duration=240, started_at="2026-10-12T11:00:00+05:30")
    tool(api, "evaluate_enquiry", "m2", "+919800000102", facts={**QUALIFIED_FACTS, "locality": "Nashik"})
    end_call(api, "m2", "+919800000102", duration=120, started_at="2026-10-11T23:00:00+05:30")  # Sunday night
    lead_id = db.row("SELECT id FROM leads WHERE call_id='m1'")["id"]
    clock.freeze(datetime(2026, 10, 12, 11, 12, tzinfo=clock.IST))
    tg_tap(api, lead_id, 1, "Asha")

    m = api.get("/api/metrics?start=2026-10-01&end=2026-10-31").json()
    assert m["volume"]["calls"] == 2 and m["after_hours"]["share_pct"] == 50.0
    assert m["funnel"]["qualified"] == 1 and m["funnel"]["booked"] == 1 and m["funnel"]["claimed"] == 1
    assert m["decline_reasons"] == {"service_area": 1}
    assert m["by_hour"][23] == 1 and m["by_hour"][11] == 1
    assert m["time_to_claim"]["handoff_to_claim"]["n"] == 1
    assert m["cost"]["complete"] is False and m["cost"]["per_call"] is None  # rate unknown → not faked

    monkeypatch.setenv("PLATFORM_COST_PER_MIN_INR", "6")
    monkeypatch.setenv("MONTHLY_FIXED_COST_INR", "3100")
    settings_mod.reload()
    m = api.get("/api/metrics?start=2026-10-01&end=2026-10-31").json()
    # 6 min × ₹6 = 36 variable; 31 days of ₹3,100/30 = 3,203.33 fixed
    assert m["cost"]["variable"] == 36.0 and m["cost"]["total"] == round(36 + 3100 * 31 / 30, 2)
    assert m["cost"]["per_booked_consultation"] == m["cost"]["total"]


def test_payload_cost_beats_configured_rate(api, monkeypatch):
    monkeypatch.setenv("PLATFORM_COST_PER_MIN_INR", "6")
    settings_mod.reload()
    end_call(api, "p1", duration=60, cost=2.5, currency="INR", started_at="2026-10-12T10:00:00+05:30")
    end_call(api, "p2", duration=60, cost=0.03, currency="USD", started_at="2026-10-12T10:05:00+05:30")
    m = api.get("/api/metrics?start=2026-10-12&end=2026-10-12").json()
    assert m["cost"]["variable"] == 2.5 + 6.0  # USD cost ignored → rate used


# ---------------------------------------------------------------- VaniAgent webhook (documented shape)
def vani_event(event, call_id, **data):
    return {"event": event, "timestamp": "2026-10-12T11:05:00+05:30",
            "data": {"call_id": call_id, "agent_id": "ag1", **data}}


def test_vaniagent_signature(api, monkeypatch):
    import hashlib, hmac, json as _json
    monkeypatch.setenv("VAANI_WEBHOOK_SECRET", "whsec")
    monkeypatch.setenv("TOOL_SECRET", "s3cret")
    settings_mod.reload()
    raw = _json.dumps(vani_event("call.completed", "v1", duration=30, status="completed")).encode()
    good = hmac.new(b"whsec", raw, hashlib.sha256).hexdigest()
    hdr = {"content-type": "application/json"}
    assert api.post("/webhooks/vaani/call-ended", content=raw, headers={**hdr, "X-Vaniagent-Signature": "bad"}).status_code == 401
    assert api.post("/webhooks/vaani/call-ended", content=raw, headers={**hdr, "X-Vaniagent-Signature": good}).status_code == 200
    assert api.post("/webhooks/vaani/call-ended", content=raw, headers=hdr).status_code == 401  # no proof at all


def test_vaniagent_info_events_have_no_side_effects(api):
    qualify(api)
    for ev in ("call.started", "transcript.ready", "recording.ready"):
        api.post("/webhooks/vaani/call-ended", json=vani_event(ev, "call-1", recording_url="https://r/1"))
    assert outbox() == [] and db.row("SELECT COUNT(*) n FROM callbacks")["n"] == 0
    api.post("/webhooks/vaani/call-ended", json=vani_event("call.completed", "call-1", duration=200, status="completed"))
    assert "hung up before booking" in outbox("telegram")[0]["body"]


def test_vaniagent_call_failed_queues_callback(api):
    api.post("/webhooks/vaani/call-ended", json=vani_event("call.failed", "f1", status="failed",
                                                          metadata={"from_number": "9800000077"}))
    assert db.row("SELECT * FROM callbacks WHERE phone='+919800000077'")


def test_webhook_links_lead_when_tools_ran_without_call_id(api):
    # Tools only got the phone (anon id); webhook arrives with the platform's real call id.
    r = api.post("/tools/evaluate_enquiry", json={"caller_phone": PHONE, "facts": QUALIFIED_FACTS}).json()
    assert r["outcome"] == "QUALIFIED"
    end_call(api, "platform-xyz", PHONE, duration=150)
    assert db.row("SELECT COUNT(*) n FROM callbacks")["n"] == 0          # no spurious "dropped" callback
    assert "hung up before booking" in outbox("telegram")[0]["body"]   # but the designer still gets it


# ---------------------------------------------------------------- VaniAgent Mode B: post-call capture
def capture(api, payload, key=None):
    url = "/webhooks/vaani/capture" + (f"?key={key}" if key else "")
    r = api.post(url, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_capture_qualified_goes_to_designers(api):
    out = capture(api, {"call_id": "vc1", "from_number": "9800000201", "extracted_fields": {
        "caller_name": "Priya", "project_category": "residential", "scope": "full_home", "locality": "Kothrud",
        "bhk": 3, "carpet_area_sqft": 1400, "deadline_text": "by March", "is_decision_maker": "yes",
        "budget_max_inr": 0, "advice_only": "no", "wants_execution": "unknown", "deadline_flexible": "unknown"}})
    assert out["outcome"] == "QUALIFIED"
    assert "please call" in outbox("telegram")[0]["body"] and "Kothrud" in outbox("telegram")[0]["body"]


def test_capture_unknowns_never_become_no(api):
    # "unknown" / 0 / "" must not turn into wants_execution=False (which would DECLINE as advice-only)
    out = capture(api, {"call_id": "vc2", "phone": "9800000202", "data": {"fields": [
        {"name": "scope", "value": "full_home"}, {"name": "locality", "value": "Baner"},
        {"name": "wants_execution", "value": "unknown"}, {"name": "deadline_text", "value": "by April"},
        {"name": "budget_max_inr", "value": 0}]}})
    assert out["outcome"] == "QUALIFIED"


def test_capture_decline_and_escalate_become_human_tasks(api):
    out = capture(api, {"call_id": "vc3", "phone": "9800000203", "locality": "Nashik", "scope": "partial",
                        "rooms_in_scope": 2})
    assert out["outcome"] == "DECLINE"
    cb = db.row("SELECT * FROM callbacks WHERE phone='+919800000203'")
    assert "post_call:decline" in cb["reason"] and not contains_price(cb["note"])
    out = capture(api, {"call_id": "vc4", "phone": "9800000204", "existing_client": "yes", "complaint": "yes",
                        "existing_client_issue": "Designer Aryan not replying"})
    assert out["outcome"] == "ESCALATE" and "URGENT" in outbox("telegram")[-1]["body"]


def test_capture_requires_key_when_secret_set(api, monkeypatch):
    monkeypatch.setenv("TOOL_SECRET", "s3cret")
    settings_mod.reload()
    assert api.post("/webhooks/vaani/capture", json={}).status_code == 401
    assert api.post("/webhooks/vaani/capture?key=wrong", json={}).status_code == 401
    assert capture(api, {"call_id": "vc5", "phone": "9800000205"}, key="s3cret")["ok"]


def test_cron_accepts_key_in_url_and_vercel_bearer(api, monkeypatch):
    monkeypatch.setenv("TOOL_SECRET", "s3cret")
    monkeypatch.setenv("CRON_SECRET", "cr0n")
    settings_mod.reload()
    assert api.post("/cron/tick").status_code == 401
    assert api.post("/cron/tick?key=s3cret").status_code == 200
    assert api.post("/cron/tick", headers={"Authorization": "Bearer cr0n"}).status_code == 200


def test_health_warns_when_serverless_without_postgres(api, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings_mod.reload()
    h = api.get("/health").json()
    assert h["persistent"] is False and "DATABASE_URL" in h["warning"]


def test_env_blob_in_single_variable_is_unpacked(api, monkeypatch):
    for k in ("PLATFORM_COST_PER_MIN_INR", "MOCK_MODE"):  # make monkeypatch restore these afterwards
        monkeypatch.setenv(k, "x")
        monkeypatch.delenv(k)
    monkeypatch.setenv("vercel_env", "# comment\nMOCK_MODE=1\nPLATFORM_COST_PER_MIN_INR=4.5\nbad line\n")
    s = settings_mod.reload()
    assert s.platform_cost_per_min == 4.5


def test_bad_database_does_not_crash_startup_and_hides_password(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:Sup3rSecretPw@127.0.0.1:1/postgres")
    monkeypatch.setenv("RUN_SCHEDULER", "0")
    settings_mod.reload()
    from app.main import app
    with TestClient(app) as c:
        h = c.get("/health").json()
        assert h["ok"] is False and "Database unreachable" in h["warning"]
        assert "Sup3rSecretPw" not in str(h)
        r = c.post("/tools/evaluate_enquiry", json={"caller_phone": PHONE, "facts": {}})
        assert r.status_code == 200 and r.json()["say"] == FALLBACK  # caller still hears the safe line


def test_capture_yes_no_strings_become_real_booleans(api):
    capture(api, {"call_id": "vb1", "phone": "9800000301", "scope": "full_home", "locality": "Baner",
                  "deadline_text": "by April", "asked_price": "no", "is_decision_maker": "no",
                  "decision_maker_will_attend": "yes"})
    lead = db.row("SELECT * FROM leads WHERE call_id='vb1'")
    assert lead["asked_price"] == 0
    facts = db.unj(lead["facts"])
    assert facts["asked_price"] is False and facts["is_decision_maker"] is False
    body = outbox("telegram")[0]["body"]
    assert "Asked about price" not in body and "represented (owners attend)" in body
