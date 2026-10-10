"""Google Sheets mirror of the lead register (one row per lead, updated in place).
SQLite stays the source of truth; the sheet is for humans. Failures here never touch a call."""
import logging

from .. import clock, db, faults
from ..settings import settings

log = logging.getLogger("aangan.sheets")

HEADER = ["lead_id", "created_at", "phone", "name", "language", "area", "project", "size_sqft",
          "timeline", "outcome", "reasons", "priority", "booked_slot", "claimed_by", "claimed_at", "notes"]


def lead_row(lead: dict) -> list:
    f = db.unj(lead.get("facts"), {})
    booking = db.row("SELECT slot_start FROM bookings WHERE id=?", lead["booking_id"]) if lead.get("booking_id") else None
    return [lead["id"], lead.get("created_at"), lead.get("phone"), f.get("caller_name"), f.get("language"),
            f.get("locality"), f.get("scope") or f.get("project_category"), f.get("carpet_area_sqft"),
            f.get("deadline_date") or f.get("deadline_text") or f.get("start_text"), lead.get("outcome"),
            ", ".join(db.unj(lead.get("reasons"), [])), "yes" if lead.get("priority") else "",
            booking["slot_start"] if booking else "", lead.get("claimed_by") or "", lead.get("claimed_at") or "",
            " | ".join(db.unj(lead.get("notes"), []))]


def mirror(lead_id: int):
    try:
        lead = db.row("SELECT * FROM leads WHERE id=?", lead_id)
        if not lead:
            return
        values = lead_row(lead)
        existing = db.row("SELECT * FROM sheet_rows WHERE lead_id=?", lead_id)
        faults.check("sheets")
        sheet_ref = existing["row"] if existing else None
        if not settings.mock_mode and settings.google_sheet_id:
            sheet_ref = _push_google(values, sheet_ref)
        if existing:
            db.update("sheet_rows", existing["id"], {"row": sheet_ref or "mock", "updated_at": clock.iso(clock.now())})
        else:
            db.insert("sheet_rows", {"lead_id": lead_id, "row": sheet_ref or "mock", "updated_at": clock.iso(clock.now())})
    except Exception as e:  # noqa: BLE001
        log.warning("sheets mirror failed for lead %s: %s", lead_id, e)
        db.insert("events", {"ts": clock.iso(clock.now()), "type": "sheets_failed", "data": str(e)[:300]})


def _push_google(values: list, row_ref: str | None) -> str:
    import google_auth_httplib2
    import httplib2
    from googleapiclient.discovery import build
    from .calendar import google_credentials
    creds = google_credentials(["https://www.googleapis.com/auth/spreadsheets"])
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=6))
    api = build("sheets", "v4", http=http, cache_discovery=False).spreadsheets().values()
    body = {"values": [[("" if v is None else v) for v in values]]}
    if row_ref and row_ref.isdigit():
        api.update(spreadsheetId=settings.google_sheet_id, range=f"Leads!A{row_ref}",
                   valueInputOption="RAW", body=body).execute()
        return row_ref
    res = api.append(spreadsheetId=settings.google_sheet_id, range="Leads!A1", valueInputOption="RAW",
                     insertDataOption="INSERT_ROWS", body=body).execute()
    rng = res.get("updates", {}).get("updatedRange", "")  # e.g. Leads!A12:P12
    return "".join(ch for ch in rng.split("!")[-1].split(":")[0] if ch.isdigit())
