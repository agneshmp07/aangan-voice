# Switching on the integrations

Everything below is built, tested, and deployed. Each integration stays **off until its key is
added**, and nothing breaks while it is off. Keys go in `.env` (local) and in the Vercel variable
`vercel_env` (Settings → Environment Variables → `vercel_env` → Edit → add the lines → Save), then
redeploy. Never paste keys into chat.

## 1 · VaniAgent browser voice ("Talk to the receptionist" page: `/dashboard/talk.html`)
1. VaniAgent → **Developer API** → **Create API Key** → copy it (shown once).
2. Add `VAANI_API_KEY=<key>` to `.env` and `vercel_env`.
3. Tell Claude "vaani key added". It then (from your machine, reading `.env`):
   - fetches the agent ID (`GET /agents`) and sets `VAANI_AGENT_ID`;
   - locks the widget to your site: `PUT /widget/config` with `allowed_origins = [https://aangan-voice-ten.vercel.app]`,
     `max_session_minutes = 5`, `max_daily_sessions = 30`.

Cost guard: each visitor gets 3 sessions per hour; 30 sessions per day in total (`WIDGET_*` settings).

## 2 · Google Calendar (consultations land on the studio calendar; busy times are never offered)
1. console.cloud.google.com → new project "aangan" → **APIs & Services → Enable APIs → Google Calendar API**
   (and **Google Sheets API** for the lead register mirror).
2. **IAM & Admin → Service accounts → Create** "aangan-bot" → **Keys → Add key → JSON** → a file downloads.
3. In Google Calendar, create a calendar "Aangan consultations" → **Settings and sharing → Share with specific
   people** → add the service account's email (…@….iam.gserviceaccount.com) → **Make changes to events**.
   Copy the **Calendar ID** from "Integrate calendar".
4. `.env`: `GOOGLE_CALENDAR_ID=<id>` and `GOOGLE_SERVICE_ACCOUNT_FILE=secrets/service-account.json` (put the file there;
   `secrets/` is git-ignored). Vercel: `GOOGLE_CALENDAR_ID=<id>` and `GOOGLE_SERVICE_ACCOUNT_JSON=<the whole file on one line>`.

What it does: free slots = working days × 11:00 / 15:00 / 17:00, minus anything busy on that calendar.
Every booking (self-booking link, or the voice tool) creates a 1-hour event with the full designer note,
tagged with the lead number. A service account can't invite guests without Google Workspace, so the caller gets
their confirmation on the booking page (and on WhatsApp from the designer).

## 3 · HubSpot CRM (Nikhil's pipeline without spreadsheets)
1. app.hubspot.com (free CRM is enough) → **Settings → Integrations → Private Apps → Create a private app** "Aangan voice".
2. Scopes: `crm.objects.contacts.read`, `crm.objects.contacts.write`, `crm.objects.deals.read`, `crm.objects.deals.write`.
   Create → copy the **access token**.
3. `.env` and `vercel_env`: `HUBSPOT_TOKEN=<token>`.
4. Optional: if your pipeline uses other stage ids (Settings → Objects → Deals → Pipelines), set
   `HUBSPOT_STAGE_QUALIFIED / _BOOKED / _WON / _LOST`.

What it does:

| Event | HubSpot |
|---|---|
| Any new enquiry (not an existing-client complaint) | Contact (found by phone first, so repeat callers aren't duplicated), lead status NEW / OPEN_DEAL / BAD_TIMING / UNQUALIFIED |
| Qualified by the rules engine | Deal "Aangan · Name · 3BHK · full home · Kothrud" in *Qualified to buy* + the designer's note on the contact timeline |
| Consultation booked (designer tap or self-booking) | Deal → *Presentation scheduled* |
| Designer taps Won / Lost | Deal → *Closed won* / *Closed lost* |
| HubSpot down | Call and Telegram handoff unaffected; the per-minute cron retries |

**No price is ever written**: the deal amount stays empty (the Cut). The designer fills it in after the consultation.
Privacy: HubSpot becomes a processor of callers' names and numbers. Mention it in the privacy notice. The admin
"delete caller" removes our copy, and the HubSpot contact is deleted in HubSpot.
