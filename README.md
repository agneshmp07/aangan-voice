# Aangan Voice Receptionist (MESA Case 03)

AI phone receptionist for Aangan Studio, Pune: answers every call 24×7 in English/Hindi,
collects the enquiry, and lets **code, not the LLM** decide against Nikhil's rubric
(`qualified.md`). Designers get a Telegram note with everything already asked; existing-client
complaints are escalated; nobody ever hears a price.

```
Caller ──► VaniAgent (voice, Gemini realtime) ──post-call fields──► /webhooks/vaani/capture
                                                                       │
                                     rules engine (backend/app/rules) ─┤ QUALIFIED → Telegram "Aangan Designers" (claim: first tap wins)
                                                                       │ ESCALATE  → Telegram "Aangan Escalations" + priority callback
                                                                       │ other     → callback task (never 9pm–9am), approved wording
                                                                       ▼
                                           Postgres (Supabase) · metrics API · dashboard
```

VaniAgent has no mid-call tools, so the engine runs **after** the call on fields VaniAgent
extracts (Mode B, see `agent/vaani_setup_guide.md` §9). The five mid-call tool endpoints
(`/tools/*`) are built and tested for platforms that support them (Mode A).

## Run locally (no accounts needed)
```bash
pip install -r requirements-dev.txt
```
```bash
python -m pytest
```
```bash
uvicorn app.main:app --app-dir backend --port 8000
```
`MOCK_MODE=1` (default) keeps Telegram/email/Calendar/Sheets in a local outbox table.
`TEST_POSTGRES=1 python -m pytest tests/test_api.py` runs the API tests on a real local Postgres.

## Deploy: GitHub → Vercel + Supabase
1. **Supabase**: new project (region Mumbai) → Project Settings → Database → Connection string →
   **Transaction pooler** (port 6543). Tables are created automatically on first request.
2. **Vercel**: Add New → Project → import this GitHub repo → Framework "Other" → add the
   environment variables below → Deploy.
3. Open `https://<project>.vercel.app/health`: expect `"database":"postgres","persistent":true`.
4. **Callbacks every minute**: Vercel Hobby cron runs once a day only, so add a free job on
   cron-job.org: `POST https://<project>.vercel.app/cron/tick?key=<TOOL_SECRET>`, every 1 minute.
5. **Telegram claim button**: open once
   `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<project>.vercel.app/webhooks/telegram&secret_token=<TELEGRAM_WEBHOOK_SECRET>`
6. **VaniAgent** → agent → Analysis & Advanced → tool `aangan_lead_sync` → webhook URL
   `https://<project>.vercel.app/webhooks/vaani/capture?key=<TOOL_SECRET>`.

| Vercel env var | Value |
|---|---|
| `DATABASE_URL` | Supabase transaction-pooler URI |
| `TOOL_SECRET`, `CRON_SECRET` | long random strings |
| `MOCK_MODE` | `0` for real Telegram/email |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DESIGNERS_CHAT_ID`, `TELEGRAM_HEAD_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET` | from `.env` |
| `PUBLIC_BASE_URL` | `https://<project>.vercel.app` |
| `PLATFORM_COST_PER_MIN_INR` | `4.5` (VaniAgent metered) |
| `VAANI_API_KEY` | optional: looks up caller numbers |
| `SMTP_*`, `DESIGNERS_EMAIL`, `HEAD_EMAIL` | optional email fallback |

## Repo map
| Path | What |
|---|---|
| `backend/app/rules/` | Rules engine, service area, timeline maths, budget check (internal only), approved lines, `contains_price()` |
| `backend/app/routers/` | Tools, webhooks (VaniAgent capture, call-ended, Telegram claim), cron, metrics API |
| `backend/app/services/` | Leads + handoff notes, callbacks queue, Telegram/email, Calendar, Sheets |
| `agent/` | VaniAgent prompt (≤800 tokens), greeting (≤150 chars), knowledge base (no pricing), setup guide |
| `tests/` | 20 phone transcripts + 3 web forms replayed, failure modes, payload shapes, agent-file checks |
| `docs/` | Analysis, nine checks, components map, handoff decision, red-team script |
| `seed/` | Case seed data (keep this repo private) |
