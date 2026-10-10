"""Designer inbox: private, shows the full call record, claim + stage with name checks."""
from app import db
from test_api import PHONE, QUALIFIED_FACTS, api, pg_url, qualify, tool  # noqa: F401 (fixtures)


def test_inbox_needs_the_key(api, monkeypatch):
    from app.settings import settings
    monkeypatch.setattr(settings, "tool_secret", "s3cret")
    assert api.get("/api/inbox").status_code == 401
    assert api.get("/api/inbox?key=s3cret").status_code == 200


def test_inbox_shows_booked_lead_with_facts_and_handles_claim_and_stage(api):
    qualify(api)
    s = tool(api, "get_consultation_slots")
    tool(api, "book_consultation", slot_id=s["slots"][0]["slot_id"])
    data = api.get("/api/inbox").json()
    item = next(i for i in data["items"] if i["id"])
    assert item["status"] == "booked" and item["phone"] == PHONE and item["booking"]
    assert any(f["label"] == "Locality" for f in item["facts"])
    lid = item["id"]
    assert api.post(f"/api/inbox/{lid}/claim", json={"who": "Riya"}).json()["ok"]
    assert not api.post(f"/api/inbox/{lid}/claim", json={"who": "Sam"}).json()["ok"]
    assert not api.post(f"/api/inbox/{lid}/stage", json={"who": "Sam", "stage": "won"}).json()["ok"]
    assert api.post(f"/api/inbox/{lid}/stage", json={"who": "Riya", "stage": "won"}).json()["ok"]
    assert api.get("/api/inbox").json()["items"][0]["status"] == "won"


def test_public_leads_feed_hides_names(api):
    qualify(api)
    names = [l["name"] for l in api.get("/api/leads").json()]
    assert all(n is None or len(n) <= 2 for n in names)
