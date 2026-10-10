"""Designer inbox: private (fails closed), shows the full call record, claim + stage with name checks."""
from app.settings import settings
from test_api import PHONE, QUALIFIED_FACTS, api, pg_url, qualify, tool  # noqa: F401 (fixtures)

K = "?key=s3cret"


def lock(monkeypatch):
    monkeypatch.setattr(settings, "tool_secret", "s3cret")


def test_inbox_locked_without_configured_key(api):
    assert api.get("/api/inbox").status_code == 503


def test_inbox_needs_the_key(api, monkeypatch):
    lock(monkeypatch)
    assert api.get("/api/inbox").status_code == 401
    assert api.get("/api/inbox" + K).status_code == 200


def test_inbox_shows_booked_lead_with_facts_and_handles_claim_and_stage(api, monkeypatch):
    qualify(api)
    s = tool(api, "get_consultation_slots")
    tool(api, "book_consultation", slot_id=s["slots"][0]["slot_id"])
    lock(monkeypatch)
    item = next(i for i in api.get("/api/inbox" + K).json()["items"] if i["id"])
    assert item["status"] == "booked" and item["phone"] == PHONE and item["booking"]
    assert any(f["label"] == "Locality" for f in item["facts"])
    lid = item["id"]
    assert api.post(f"/api/inbox/{lid}/claim" + K, json={"who": "Riya"}).json()["ok"]
    assert not api.post(f"/api/inbox/{lid}/claim" + K, json={"who": "Sam"}).json()["ok"]
    assert not api.post(f"/api/inbox/{lid}/stage" + K, json={"who": "Sam", "stage": "won"}).json()["ok"]
    assert api.post(f"/api/inbox/{lid}/stage" + K, json={"who": "Riya", "stage": "won"}).json()["ok"]
    assert api.get("/api/inbox" + K).json()["items"][0]["status"] == "won"


def test_public_leads_feed_hides_names(api, monkeypatch):
    qualify(api)
    lock(monkeypatch)
    names = [l["name"] for l in api.get("/api/leads").json()]
    assert names and all(n is None or len(n) <= 2 for n in names)
    full = [l["name"] for l in api.get("/api/leads" + K).json()]
    assert any(n and len(n) > 2 for n in full)
