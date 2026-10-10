"""HubSpot CRM sync and Google Calendar booking."""
import json
from datetime import datetime

import httpx

from app import clock, db, settings as settings_mod
from app.faults import FAULTS
from app.rules.price_guard import contains_price
from app.services import calendar, hubspot, leads, notify
from test_api import PHONE, QUALIFIED_FACTS, api, capture, outbox, pg_url, tg_tap  # noqa: F401 (fixtures)


def with_hubspot(monkeypatch):
    monkeypatch.setenv("HUBSPOT_TOKEN", "pat-test")
    settings_mod.reload()


def hs_calls():
    return [(r["subject"], r["recipient"], json.loads(r["body"])) for r in outbox("hubspot")]


QUAL = {"call_id": "h1", "phone": "9800000701", "caller_name": "Priya Kulkarni", "scope": "full_home", "bhk": 3,
        "locality": "Kothrud", "deadline_text": "by March", "is_decision_maker": "yes"}


# ---------------------------------------------------------------- HubSpot
def test_qualified_lead_becomes_contact_deal_and_note(api, monkeypatch):
    with_hubspot(monkeypatch)
    out = capture(api, QUAL)
    assert out["outcome"] == "QUALIFIED" and "hubspot:ok" in out["actions"]
    calls = hs_calls()
    paths = [(m, p) for m, p, _ in calls]
    assert ("POST", "/crm/v3/objects/contacts/search") in paths and ("POST", "/crm/v3/objects/contacts") in paths
    deal = next(b for m, p, b in calls if p == "/crm/v3/objects/deals")
    assert deal["properties"]["dealstage"] == "qualifiedtobuy" and "amount" not in deal["properties"]
    assert deal["associations"][0]["types"][0]["associationTypeId"] == 3
    contact = next(b for m, p, b in calls if p == "/crm/v3/objects/contacts")
    assert contact["properties"]["firstname"] == "Priya" and contact["properties"]["hs_lead_status"] == "OPEN_DEAL"
    note = next(b for m, p, b in calls if p == "/crm/v3/objects/notes")
    assert "Kothrud" in note["properties"]["hs_note_body"]
    lead = db.row("SELECT * FROM leads WHERE call_id='h1'")
    assert lead["hubspot_contact_id"] and lead["hubspot_deal_id"] and lead["hubspot_synced_at"]
    for _, _, b in calls:  # the Cut: no price ever leaves the system
        assert not contains_price(json.dumps(b))


def test_designer_taps_move_the_deal(api, monkeypatch):
    with_hubspot(monkeypatch)
    lead_id = capture(api, QUAL)["lead_id"]
    tg_tap(api, lead_id, 1, "Asha")
    api.post("/webhooks/telegram", json={"callback_query": {"id": "x", "data": f"stage:{lead_id}:won",
             "from": {"id": 1, "first_name": "Asha"}, "message": {"message_id": 1, "chat": {"id": -1}, "text": "t"}}})
    deal_id = leads.by_id(lead_id)["hubspot_deal_id"]
    patches = [b for m, p, b in hs_calls() if m == "PATCH" and p == f"/crm/v3/objects/deals/{deal_id}"]
    assert patches and patches[-1]["properties"]["dealstage"] == "closedwon"


def test_declined_is_contact_only_and_escalation_is_skipped(api, monkeypatch):
    with_hubspot(monkeypatch)
    capture(api, {"call_id": "h2", "phone": "9800000702", "scope": "full_home", "locality": "Nashik"})
    c = [b for m, p, b in hs_calls() if p == "/crm/v3/objects/contacts"]
    assert c and c[-1]["properties"]["hs_lead_status"] == "UNQUALIFIED"
    assert not [p for _, p, _ in hs_calls() if p == "/crm/v3/objects/deals"]
    n = len(hs_calls())
    capture(api, {"call_id": "h3", "phone": "9800000703", "existing_client": "yes", "complaint": "yes",
                  "existing_client_issue": "Delay"})
    assert len(hs_calls()) == n


def test_hubspot_down_never_breaks_the_call_and_cron_retries(api, monkeypatch):
    with_hubspot(monkeypatch)
    FAULTS["hubspot"] = "error"
    out = capture(api, QUAL)
    assert out["outcome"] == "QUALIFIED" and "hubspot:failed" in out["actions"]
    assert "Kothrud" in outbox("telegram")[0]["body"]  # the designer still got the lead
    assert db.row("SELECT hubspot_synced_at FROM leads WHERE call_id='h1'")["hubspot_synced_at"] is None
    FAULTS.clear()
    assert api.post("/cron/tick").json()["hubspot_retried"] == 1
    assert db.row("SELECT hubspot_deal_id FROM leads WHERE call_id='h1'")["hubspot_deal_id"]


def test_real_hubspot_request_shape(api, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    with_hubspot(monkeypatch)
    seen = []

    def fake_request(method, url, json=None, timeout=None, headers=None):
        seen.append((method, url, headers, json))
        body = {"results": []} if url.endswith("/search") else {"id": str(len(seen))}
        return httpx.Response(200, json=body, request=httpx.Request(method, url))
    monkeypatch.setattr(hubspot.httpx, "request", fake_request)
    lead = leads.get_or_create("real1", "+919800000704")
    leads.decide(lead, {**QUALIFIED_FACTS})
    res = hubspot.sync_lead(lead["id"])
    assert res["contact"] and res["deal"]
    assert all(u.startswith("https://api.hubapi.com/crm/v3/objects/") for _, u, _, _ in seen)
    assert seen[0][2]["Authorization"] == "Bearer pat-test"


def test_hubspot_off_without_token(api):
    capture(api, QUAL)
    assert outbox("hubspot") == []


# ---------------------------------------------------------------- Google Calendar
class FakeCal:
    def __init__(self, busy):
        self.busy, self.inserted = busy, []

    def freebusy(self):
        cal = self
        class Q:
            def query(self, body):
                class X:
                    def execute(_):
                        return {"calendars": {settings_mod.settings.google_calendar_id: {"busy": cal.busy}}}
                return X()
        return Q()

    def events(self):
        cal = self
        class E:
            def insert(self, calendarId, body):
                cal.inserted.append((calendarId, body))
                class X:
                    def execute(_):
                        return {"id": "gcal-123"}
                return X()
        return E()


def test_google_calendar_busy_blocks_and_event(api, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "0")
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "studio@group.calendar.google.com")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    settings_mod.reload()
    fake = FakeCal([{"start": "2026-10-12T15:00:00+05:30", "end": "2026-10-12T16:00:00+05:30"}])  # Nikhil busy at 3 pm
    monkeypatch.setattr(calendar, "_google", lambda: fake)
    slots = [s["slot_id"] for s in calendar.free_slots()]
    assert "2026-10-12T15:00:00+05:30" not in slots and "2026-10-12T17:00:00+05:30" in slots
    lead = leads.get_or_create("cal1", PHONE)
    leads.decide(lead, {**QUALIFIED_FACTS})
    ok, bid = leads.book_slot(leads.by_id(lead["id"]), clock.parse("2026-10-12T17:00:00+05:30"), source="self")
    assert ok
    cal_id, body = fake.inserted[0]
    assert cal_id == "studio@group.calendar.google.com" and body["start"]["timeZone"] == "Asia/Kolkata"
    assert body["extendedProperties"]["private"]["aangan_lead_id"] == str(lead["id"])
    assert "Kothrud" in body["description"] and not contains_price(body["description"])
    assert db.row("SELECT calendar_event_id FROM bookings WHERE id=?", bid)["calendar_event_id"] == "gcal-123"
