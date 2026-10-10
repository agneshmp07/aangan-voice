"""HubSpot CRM sync: every enquiry becomes a contact; every qualified lead becomes a deal that
follows the designer's Booked / Won / Lost taps.

API (HubSpot CRM v3, private-app token as Bearer):
  POST /crm/v3/objects/contacts/search   find by phone (dedupe repeat callers)
  POST /crm/v3/objects/contacts          create      PATCH /crm/v3/objects/contacts/{id}  update
  POST /crm/v3/objects/deals             create with association to the contact (type 3: deal→contact)
  PATCH /crm/v3/objects/deals/{id}       move stage
  POST /crm/v3/objects/notes             the designer handoff note, associated to the contact (type 202)

Rules:
- Never send a price. The deal `amount` stays empty (the Cut); the designer sets it after the consultation.
- Existing-client escalations are not new leads: no contact/deal is created from them.
- Failures never touch a call: everything is logged, and the cron retries unsynced leads.
- Stage names are configurable (HUBSPOT_STAGE_*), because every HubSpot portal can rename its pipeline.
"""
import json
import logging

import httpx

from .. import clock, db, faults
from ..settings import settings

log = logging.getLogger("aangan.hubspot")
BASE = "https://api.hubapi.com"

LEAD_STATUS = {"QUALIFIED": "OPEN_DEAL", "ASK": "NEW", "NURTURE": "BAD_TIMING", "DECLINE": "UNQUALIFIED"}


def enabled() -> bool:
    return bool(settings.hubspot_token)  # in MOCK_MODE the requests go to the outbox instead of HubSpot


def _stage_for(lead: dict) -> str:
    stage = lead.get("stage")
    if stage == "won":
        return settings.hubspot_stage_won
    if stage == "lost":
        return settings.hubspot_stage_lost
    if stage == "booked" or lead.get("booking_id"):
        return settings.hubspot_stage_booked
    return settings.hubspot_stage_qualified


def _req(method: str, path: str, body: dict | None = None) -> dict:
    faults.check("hubspot")
    if settings.mock_mode:
        db.insert("outbox", dict(channel="hubspot", recipient=path, subject=method, body=json.dumps(body or {}, ensure_ascii=False),
                                 ref="hubspot", status="mock_sent", created_at=clock.iso(clock.now())))
        if path.endswith("/search"):
            return {"results": []}
        return {"id": f"mock-{abs(hash((path, json.dumps(body or {}, sort_keys=True)))) % 10**8}"}
    r = httpx.request(method, BASE + path, json=body, timeout=8,
                      headers={"Authorization": f"Bearer {settings.hubspot_token}", "Content-Type": "application/json"})
    if r.status_code >= 400:
        raise RuntimeError(f"hubspot {method} {path}: {r.status_code} {r.text[:200]}")
    return r.json() if r.text else {}


def _contact_props(lead: dict) -> dict:
    f = db.unj(lead.get("facts"), {})
    name = (f.get("caller_name") or "").strip()
    first, _, last = name.partition(" ")
    props = {
        "phone": lead.get("phone"),
        "firstname": first or None, "lastname": last or None,
        "city": f.get("locality"),
        "hs_lead_status": LEAD_STATUS.get(lead.get("outcome") or "", "NEW"),
        "lifecyclestage": "salesqualifiedlead" if lead.get("outcome") == "QUALIFIED" else "lead",
    }
    return {k: v for k, v in props.items() if v not in (None, "")}


def _deal_props(lead: dict) -> dict:
    f = db.unj(lead.get("facts"), {})
    bits = [f.get("caller_name") or lead.get("phone"), f.get("bhk") and f"{f['bhk']}BHK", f.get("scope"), f.get("locality")]
    return {"dealname": "Aangan · " + " · ".join(str(b).replace("_", " ") for b in bits if b),
            "pipeline": settings.hubspot_pipeline, "dealstage": _stage_for(lead)}  # no amount: never a price


def sync_lead(lead_id: int) -> dict:
    """Idempotent: creates or updates the contact, then the deal for qualified leads."""
    if not enabled():
        return {"skipped": "no token"}
    lead = db.row("SELECT * FROM leads WHERE id=?", lead_id)
    if not lead or lead.get("outcome") in (None, "ESCALATE") or not lead.get("phone"):
        return {"skipped": "not a new enquiry"}
    try:
        cid = lead.get("hubspot_contact_id")
        props = _contact_props(lead)
        if not cid:
            found = _req("POST", "/crm/v3/objects/contacts/search", {"filterGroups": [{"filters": [
                {"propertyName": "phone", "operator": "EQ", "value": lead["phone"]}]}], "limit": 1})
            cid = (found.get("results") or [{}])[0].get("id")
        if cid:
            _req("PATCH", f"/crm/v3/objects/contacts/{cid}", {"properties": props})
        else:
            cid = _req("POST", "/crm/v3/objects/contacts", {"properties": props})["id"]
        upd = {"hubspot_contact_id": cid, "hubspot_synced_at": clock.iso(clock.now())}
        did = lead.get("hubspot_deal_id")
        if lead.get("outcome") == "QUALIFIED":
            if did:
                _req("PATCH", f"/crm/v3/objects/deals/{did}", {"properties": _deal_props(lead)})
            else:
                did = _req("POST", "/crm/v3/objects/deals", {"properties": _deal_props(lead), "associations": [
                    {"to": {"id": cid}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]}]})["id"]
                upd["hubspot_deal_id"] = did
                _note(lead, cid)
        db.update("leads", lead_id, upd)
        return {"contact": cid, "deal": did}
    except Exception as e:  # noqa: BLE001 — the CRM must never break a call
        log.warning("hubspot sync failed for lead %s: %s", lead_id, e)
        db.insert("events", {"ts": clock.iso(clock.now()), "type": "hubspot_failed", "data": f"lead {lead_id}: {str(e)[:250]}"})
        return {"error": str(e)[:200]}


def _note(lead: dict, contact_id: str):
    """The same note the designer gets on Telegram, attached to the contact's timeline."""
    from .leads import handoff_text
    _, plain = handoff_text(lead, "qualified_unbooked")
    _req("POST", "/crm/v3/objects/notes", {
        "properties": {"hs_timestamp": clock.now().isoformat(), "hs_note_body": plain[:60000]},
        "associations": [{"to": {"id": contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]})


def retry_unsynced(limit: int = 20) -> int:
    """Cron backstop: anything decided but never synced (HubSpot was down, token added later)."""
    if not enabled():
        return 0
    rows = db.rows("SELECT id FROM leads WHERE outcome IS NOT NULL AND outcome!='ESCALATE' AND phone IS NOT NULL "
                   "AND hubspot_synced_at IS NULL ORDER BY id LIMIT ?", limit)
    for r in rows:
        sync_lead(r["id"])
    return len(rows)
