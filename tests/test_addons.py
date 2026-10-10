"""Add-ons: designer pipeline + ROI, self-booking link, weekly summary, editable rules, privacy, browser voice."""
import json
from datetime import datetime, timedelta

import httpx
import pytest

from app import clock, db, settings as settings_mod
from app.rules import overrides
from app.services import leads, notify
from test_api import PHONE, QUALIFIED_FACTS, api, capture, outbox, pg_url, qualify, tg_tap, tool  # noqa: F401 (fixtures)


def tg_stage(api, lead_id, user_id, name, stage):
    return api.post("/webhooks/telegram", json={"callback_query": {
        "id": f"s{user_id}", "data": f"stage:{lead_id}:{stage}", "from": {"id": user_id, "first_name": name},
        "message": {"message_id": 1, "chat": {"id": -100}, "text": "lead"}}}).json()


# ---------------------------------------------------------------- designer pipeline + ROI
def test_claim_then_stage_buttons_and_only_claimer_can_update(api):
    lead_id = qualify(api)["lead_id"]
    assert tg_tap(api, lead_id, 1, "Asha")["won"]
    ans = outbox("telegram")[-1]
    assert "stage:" in (ans["external_id"] or "")  # claim edit carries the Booked/Won/Lost buttons
    assert tg_stage(api, lead_id, 2, "Rohan", "won")["ok"] is False  # not the claimer
    assert tg_stage(api, lead_id, 1, "Asha", "booked")["ok"]
    assert tg_stage(api, lead_id, 1, "Asha", "won")["ok"]
    assert leads.by_id(lead_id)["stage"] == "won"


def test_stage_before_claim_is_refused(api):
    lead_id = qualify(api)["lead_id"]
    assert tg_stage(api, lead_id, 1, "Asha", "won")["ok"] is False


def test_metrics_pipeline_and_roi(api, monkeypatch):
    monkeypatch.setenv("PLATFORM_COST_PER_MIN_INR", "4.5")
    monkeypatch.setenv("MONTHLY_FIXED_COST_INR", "0")
    settings_mod.reload()
    a = qualify(api, "w1", "+919800000401")["lead_id"]
    b = qualify(api, "w2", "+919800000402")["lead_id"]
    api.post("/webhooks/vaani/call-ended", json={"call_id": "w1", "from_number": "+919800000401", "duration": 300,
                                                 "started_at": "2026-10-12T11:00:00+05:30"})
    tg_tap(api, a, 1, "Asha"); tg_stage(api, a, 1, "Asha", "won")
    tg_tap(api, b, 2, "Rohan"); tg_stage(api, b, 2, "Rohan", "lost")
    m = api.get("/api/metrics?start=2026-10-01&end=2026-10-31").json()
    p = m["pipeline"]
    assert p["won"] == 1 and p["lost"] == 1 and p["win_rate_pct"] == 50.0
    assert p["est_revenue_inr"] == 1_100_000
    assert m["cost"]["per_won_project"] == m["cost"]["total"] and m["cost"]["roi_multiple"] > 1000


def test_email_fallback_stage_link(api):
    lead_id = qualify(api)["lead_id"]
    api.get(f"/claim/{lead_id}?by=Asha&t={notify.claim_token(lead_id)}")
    assert api.get(f"/stage/{lead_id}?s=won&by=Asha&t=bad").status_code == 403
    r = api.get(f"/stage/{lead_id}?s=won&by=Asha&t={notify.sign('stage', lead_id)}")
    assert "Saved" in r.text and leads.by_id(lead_id)["stage"] == "won"


# ---------------------------------------------------------------- self-booking
def test_handoff_carries_whatsapp_booking_button(api):
    qualify(api)
    api.post("/webhooks/vaani/call-ended", json={"call_id": "call-1", "from_number": PHONE, "duration": 120})
    sent = outbox("telegram")[0]
    markup = json.loads(sent["subject"])
    urls = [b.get("url") for row in markup["inline_keyboard"] for b in row if b.get("url")]
    assert urls and urls[0].startswith("https://wa.me/919800000001?text=")
    assert "/book/" in urls[0] and "Rs" not in urls[0]


def test_self_booking_flow(api):
    lead_id = qualify(api)["lead_id"]
    tok = notify.sign("book", lead_id)
    assert api.get(f"/book/{lead_id}?t=wrong").status_code == 403
    page = api.get(f"/book/{lead_id}?t={tok}")
    assert page.status_code == 200 and "pick a time" in page.text and "Monday 12 October at 3 pm" in page.text
    r = api.post(f"/book/{lead_id}", data={"t": tok, "slot": "2026-10-12T15:00:00+05:30"})
    assert "You're booked" in r.text
    lead = leads.by_id(lead_id)
    assert lead["booking_id"] and lead["self_booked"] == 1 and lead["stage"] == "booked"
    assert "Caller self-booked" in outbox("telegram")[-1]["body"]
    again = api.post(f"/book/{lead_id}", data={"t": tok, "slot": "2026-10-13T11:00:00+05:30"})
    assert "already booked" in again.text


def test_self_booking_rechecks_the_rules(api):
    out = capture(api, {"call_id": "nb1", "phone": "9800000501", "scope": "full_home", "locality": "Nashik"})
    lead_id = out["lead_id"]
    page = api.get(f"/book/{lead_id}?t={notify.sign('book', lead_id)}")
    assert "Our team will call you" in page.text
    r = api.post(f"/book/{lead_id}", data={"t": notify.sign("book", lead_id), "slot": "2026-10-12T15:00:00+05:30"})
    assert "call you" in r.text and not leads.by_id(lead_id)["booking_id"]


# ---------------------------------------------------------------- weekly summary
def test_weekly_summary_goes_to_head(api):
    qualify(api)
    r = api.post("/cron/weekly").json()
    assert r["ok"]
    body = outbox("telegram")[-1]["body"]
    assert "last 7 days" in body and "qualified" in body


# ---------------------------------------------------------------- editable rules
@pytest.fixture()
def admin(api, monkeypatch):
    monkeypatch.setenv("TOOL_SECRET", "adm1n")
    settings_mod.reload()
    overrides.reset_cache()
    yield api
    overrides.reset_cache()


def test_admin_requires_key(admin):
    assert admin.get("/admin").status_code == 401
    assert admin.get("/admin?key=wrong").status_code == 401
    assert "Rules" in admin.get("/admin?key=adm1n").text


def test_admin_rule_change_changes_decisions(admin):
    h = {"X-Aangan-Secret": "adm1n"}
    facts = {**QUALIFIED_FACTS, "deadline_date": "2026-12-28", "deadline_flexible": False, "deadline_text": None}  # ~11 weeks
    r1 = admin.post("/tools/evaluate_enquiry", headers=h, json={"call_id": "r1", "caller_phone": PHONE, "facts": facts}).json()
    assert r1["outcome"] == "QUALIFIED"
    admin.post("/admin/rules?key=adm1n", data={"min_weeks_to_completion": "12", "extra_out_areas": "Kothrud"})
    r2 = admin.post("/tools/evaluate_enquiry", headers=h, json={"call_id": "r2", "caller_phone": "+919800000601", "facts": facts}).json()
    assert r2["outcome"] == "DECLINE" and set(r2["reasons"]) == {"timeline", "service_area"}
    assert db.row("SELECT COUNT(*) AS n FROM events WHERE type='rules_changed'")["n"] == 1


def test_admin_rejects_out_of_range(admin):
    r = admin.post("/admin/rules?key=adm1n", data={"min_weeks_to_completion": "2"})
    assert "between 4 and 26" in r.text
    assert db.row("SELECT COUNT(*) AS n FROM rule_overrides")["n"] == 0


# ---------------------------------------------------------------- privacy
def test_delete_caller_erases_everything(admin):
    h = {"X-Aangan-Secret": "adm1n"}
    admin.post("/tools/evaluate_enquiry", headers=h, json={"call_id": "p1", "caller_phone": PHONE, "facts": QUALIFIED_FACTS})
    admin.post("/webhooks/vaani/call-ended?key=adm1n", json={"call_id": "p1", "from_number": PHONE, "duration": 90})
    r = admin.post("/admin/delete-caller?key=adm1n", data={"phone": "98000 00001"})
    assert "records about that number were deleted" in r.text
    for t in ("leads", "calls", "callbacks"):
        assert db.row(f"SELECT COUNT(*) AS n FROM {t} WHERE phone=?", PHONE)["n"] == 0


def test_retention_purges_old_transcripts(api):
    api.post("/webhooks/vaani/call-ended", json={"call_id": "old", "from_number": PHONE, "duration": 60,
                                                 "transcript": "hello", "recording_url": "https://r/1"})
    from app.routers.pages import purge_old
    assert purge_old(clock.now() + timedelta(days=200)) == 1
    row = db.row("SELECT transcript, recording_url, purged FROM calls WHERE id='old'")
    assert row["transcript"] is None and row["recording_url"] is None and row["purged"] == 1


# ---------------------------------------------------------------- browser voice (VaniAgent widget)
def test_widget_off_without_key(api):
    assert api.get("/api/vaani/status").json()["enabled"] is False
    assert api.post("/api/vaani/session").status_code == 503


def test_vaani_webrtc_session_and_limits(api, monkeypatch):
    monkeypatch.setenv("VAANI_API_KEY", "vaani_test")
    monkeypatch.setenv("VAANI_AGENT_ID", "8cf3373e-eb6f-4b4c-9f3c-324a56a91147")
    settings_mod.reload()
    from app.routers import vaani_widget
    vaani_widget._recent.clear()
    seen = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        seen.update(url=url, headers=headers, json=json)
        return httpx.Response(200, json={"token": "lk-tok", "room_name": "web-room-1", "connection_url": "wss://lk.example",
                                         "live_captions_url": "https://cap.example/x"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(vaani_widget.httpx, "post", fake_post)
    assert api.get("/api/vaani/status").json() == {"enabled": True, "max_minutes": 5, "provider": "vaani"}
    r = api.post("/api/vaani/session", json={"language": "en"})
    assert r.status_code == 200 and r.json()["token"] == "lk-tok" and r.json()["connection_url"] == "wss://lk.example"
    assert seen["url"] == "https://api.vaanivoice.ai/api/trigger-call/" and seen["headers"]["X-API-Key"] == "vaani_test"
    assert seen["json"]["medium"] == "webrtc" and seen["json"]["agent_id"].startswith("8cf3373e")
    assert "vaani_test" not in r.text  # the API key never reaches the browser
    assert db.row("SELECT id FROM calls WHERE id='web-room-1'")  # browser call is tracked like a phone call
    api.post("/api/vaani/session"); api.post("/api/vaani/session")
    assert api.post("/api/vaani/session").status_code == 429  # per-visitor limit


# ---------------------------------------------------------------- Vaani webhook lifecycle
def vaani(api, body):
    r = api.post("/webhooks/vaani", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_vaani_call_lifecycle_qualified(api):
    vaani(api, {"event": "call_started", "room_name": "room_1", "status": "active", "phone_number": "+919800000901"})
    vaani(api, {"event": "call_ended", "room_name": "room_1", "call_duration": 182.5, "end_reason": "USER_HANGUP"})
    out = vaani(api, {"event": "call_postprocessing", "call_id": "room_1", "data": {
        "room_name": "room_1", "call_id": "room_1", "call_duration": 182500.0, "summary": "3BHK in Kothrud",
        "recording_url": "https://rec/1", "transcript": "AGENT: Namaste ...",
        "entities": {"caller_name": "Priya", "scope": "full_home", "locality": "Kothrud", "bhk": 3,
                     "deadline_text": "by March", "is_decision_maker": "yes", "asked_price": "no"},
        "dispositions": {"outcome": "new_enquiry"}}})
    assert out["outcome"] == "QUALIFIED" and "handoff_designers" in out["actions"]
    call = db.row("SELECT * FROM calls WHERE id='room_1'")
    assert call["phone"] == "+919800000901" and call["duration_s"] == 182.5 and call["recording_url"] == "https://rec/1"
    lead = db.row("SELECT * FROM leads WHERE call_id='room_1'")
    assert lead["phone"] == "+919800000901" and lead["asked_price"] == 0
    note = outbox("telegram")[0]["body"]
    assert "Priya" in note and "Kothrud" in note and "3BHK in Kothrud" in note  # Vaani's summary rides along


def test_vaani_silent_call_gets_one_callback(api):
    vaani(api, {"event": "call_started", "room_name": "room_2", "phone_number": "+919800000902"})
    out = vaani(api, {"event": "call_postprocessing", "call_id": "room_2", "data": {"room_name": "room_2",
                      "call_duration": 9000, "end_reason": "silence", "entities": {}}})
    assert out["actions"][0].startswith("callback:")
    vaani(api, {"event": "call_postprocessing", "call_id": "room_2", "data": {"room_name": "room_2", "entities": {}}})
    assert db.row("SELECT COUNT(*) AS n FROM callbacks WHERE phone='+919800000902'")["n"] == 1


def test_vaani_requires_key_when_secret_set(api, monkeypatch):
    monkeypatch.setenv("TOOL_SECRET", "s3cret")
    settings_mod.reload()
    assert api.post("/webhooks/vaani", json={"event": "call_started", "room_name": "r"}).status_code == 401
    assert api.post("/webhooks/vaani?key=s3cret", json={"event": "call_started", "room_name": "r"}).status_code == 200


def test_real_vaani_call_links_phoneless_tool_lead_and_skips_false_callback(api):
    """Replays the 2026-10-10 test call: tools carry only session_ref (no call id, no phone);
    the webhook brings the phone; call_duration is in seconds; entities is null."""
    vaani(api, {"event": "call_started", "room_name": "outbound-1", "phone_number": "+919480428173"})
    flat = {"language": "en", "session_ref": "A82K", **{k: ("yes" if v is True else "no" if v is False else v)
                                                        for k, v in QUALIFIED_FACTS.items() if v is not None}}
    assert api.post("/tools/evaluate_enquiry", json=flat).json()["outcome"] == "QUALIFIED"
    s = api.post("/tools/get_consultation_slots", json={"language": "en", "session_ref": "A82K", "slot_id": ""}).json()
    b = api.post("/tools/get_consultation_slots", json={"language": "en", "session_ref": "A82K",
                                                        "slot_id": s["slots"][0]["slot_id"]}).json()
    assert b["ok"] and b.get("booking_id")
    vaani(api, {"event": "call_postprocessing", "call_id": "outbound-1", "data": {
        "room_name": "outbound-1", "call_duration": 126.17, "summary": "Booked.", "entities": None}})
    lead = db.row("SELECT * FROM leads WHERE call_id='vref-A82K'")
    assert lead["phone"] == "+919480428173"
    assert db.row("SELECT COUNT(*) n FROM callbacks")["n"] == 0
    assert db.row("SELECT duration_s FROM calls WHERE id='outbound-1'")["duration_s"] == 126.2
