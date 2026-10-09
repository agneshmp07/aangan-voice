# VaniAgent setup guide: Aangan voice receptionist

Platform: **VaniAgent** (vaniagent.com · api.vaniagent.com · Solvea Technologies).
Every claim below is tagged:

- **[Docs]** = read in VaniAgent's public pages on 2026-10-10 (vaniagent.com, /resources/api-docs).
- **[Check]** = not in the public docs. Look for it in your dashboard, or ask support@vaniagent.com.
- **[Recommend]** = my recommended value, with the reason.

---

## 0 · The one question that decides the build (do this first) [Check]

The public API docs describe agents (`prompt`, `voice`, `language`, `temperature`, `max_duration`),
outbound calls and webhooks. **They do not describe the agent calling an HTTP tool in the middle
of a call.** The marketing page lists "Custom APIs", "Developer API", "Webhooks", "Human Handoff"
and "Lead Routing", so it may exist in the dashboard.

In your agent's settings, look for **Tools / Functions / Actions / Custom API / API calls / Integrations**.

| What you find | Mode | What works |
|---|---|---|
| The agent can call an HTTPS URL mid-call and read the JSON reply | **Mode A (full build)** | Everything: live qualification by the rules engine, live booking, live escalation |
| Only post-call webhooks | **Mode B (fallback)** | Bot collects facts and promises a callback; the rules engine runs after the call; designers book by phone. See §9. |

Also check whether the tool request can include **call id** and **caller number** variables.
Both are optional: the backend links calls by phone number if the id is missing. Without the
caller number, though, callbacks can't be queued from tool failures. The end-of-call webhook still
recovers it through `GET /v1/calls/:id`.

---

## 1 · Put the backend online

VaniAgent needs a public **HTTPS** URL for tools and webhooks [Docs: webhooks must be HTTPS].

**For the class demo (free, 5 min): ngrok**
```bash
cd aangan-voice && pip install -r requirements.txt
```
```bash
uvicorn app.main:app --app-dir backend --port 8000
```
```bash
ngrok http 8000
```
Copy the `https://….ngrok-free.app` URL into `.env` as `PUBLIC_BASE_URL`. It changes every
time ngrok restarts. Re-paste it into VaniAgent and Telegram when it does.

**For real use: Render or Railway, about ₹600–800/month [Likely]**
- Use a **paid always-on instance**. Free tiers sleep and take 30–60 s to wake: the first tool
  call after a quiet night would blow the 4-second rule.
- SQLite needs a **persistent disk** (Render: add a Disk, set `DB_PATH=/data/aangan.db`).
- Start command: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
- Copy every value from your local `.env` into the host's environment settings. Never upload `.env`.
- Put the monthly hosting cost in `MONTHLY_FIXED_COST_INR` so the dashboard counts the tool's own cost.

Check it's up: open `{PUBLIC_BASE_URL}/health` → `{"ok": true}`.

---

## 2 · Connect Telegram's claim button
Open once in a browser (your token, your URL, the `TELEGRAM_WEBHOOK_SECRET` from `.env`):
```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<PUBLIC_BASE_URL>/webhooks/telegram&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```
Expect `{"ok":true,"result":true,"description":"Webhook was set"}`.
(After this, the `getUpdates` page stops working. That's normal.)

---

## 3 · Create the agent in VaniAgent

| Field | Value | Tag |
|---|---|---|
| Name | Aangan Studio Receptionist | |
| Prompt | Everything below the line in `agent/system_prompt.md` | [Docs: `prompt`] |
| First message / greeting | The bilingual one in `agent/first_message.md` | [Check: not in API docs; usually in the dashboard] |
| Language | Hindi + English (Indian English). If only one can be chosen, pick **Hindi (hi-IN)** with code-switching / "multilingual" if offered | [Docs: `language`] [Recommend] |
| Voice | A **female**, Indian-accented voice that speaks both Hindi and English. The Hindi lines use feminine verb forms ("रही हूँ") | [Docs: `voice`] [Recommend] |
| Temperature | **0.3**. The docs' example is 0.7. Lower means it follows the script and speaks `say` verbatim | [Docs: `temperature`] [Recommend] |
| Max duration | **600 s** (10 min). The longest September call was 7.5 min | [Docs: `max_duration`] [Recommend] |
| Knowledge base | Upload `agent/knowledge_base.md`. **Never upload `pricing.md`** | [Check] |

### Voice-behaviour settings (names vary by platform) [Check] [Recommend]

| Setting | Value | Why |
|---|---|---|
| **Endpointing** (how long a pause counts as "finished speaking") | **600–800 ms** | Indian callers often pause mid-sentence while thinking of an area name or a number. Below ~500 ms the bot cuts them off |
| **Interruptions / barge-in** | **On**, minimum about **2 words or 400 ms** of speech before it stops talking | Lets callers interrupt; stops coughs, "hmm" and traffic noise from cutting the bot off |
| **Silence timeout** | Re-prompt after **7 s**, end the call after about **20 s** total silence | The prompt says "Are you still there?" once; the webhook then queues the callback |
| **Backchannel / filler while thinking** | On, if offered | Covers tool latency (≤ 3.5 s by design) |
| **Speech-to-text** | Bundled in VaniAgent's per-minute price, and the provider isn't named [Docs]. If you can choose: a model trained on **Indian English + Hindi code-mixing**. Test with real Pune place names (Pimple Saudagar, Kalyani Nagar, Hinjewadi) | [Check] |
| **Custom vocabulary / keywords** | Add every locality from `knowledge_base.md`, plus "Aangan", "BHK", "carpet area", "modular kitchen", "wardrobe" | Place names are where speech-to-text fails first |
| **Recording** | On (the greeting discloses it) | Recording link goes into the designer's note |
| **Call analysis / sentiment** | On, if free | VaniAgent lists `sentiment` on calls [Docs]; useful for the red-team review |

---

## 4 · Add the five tools (Mode A only)

For each tool in `agent/tools.json`:
- **URL:** `{PUBLIC_BASE_URL}/tools/<name>` (e.g. `/tools/evaluate_enquiry`)
- **Method:** POST, body JSON
- **Header:** `X-Aangan-Secret: <TOOL_SECRET from .env>`. If only a bearer token is allowed, use `Authorization: Bearer <TOOL_SECRET>`; the backend accepts both.
- **Parameters:** paste the `parameters` JSON schema
- **Timeout:** 4–5 s if configurable. Our worst case is 3.5 s.
- **Response:** tell the agent to read `say` from the JSON and speak it.
- **Variables:** map call id → `call_id` and caller number → `caller_phone` if the dashboard offers them.

---

## 5 · End-of-call webhook

VaniAgent: **Dashboard → Settings → Webhooks** [Docs]
- URL: `{PUBLIC_BASE_URL}/webhooks/vaani/call-ended`
- Events: **`call.completed`, `call.failed`**, plus `transcript.ready` and `recording.ready` (stored, no actions)
- Secret: copy VaniAgent's webhook secret into `.env` as `VAANI_WEBHOOK_SECRET`. The backend verifies the
  `X-Vaniagent-Signature` header (HMAC-SHA256 of the body) [Docs].
- Use VaniAgent's **"send test"** button if it has one. You should see a row appear on the dashboard.

The documented payload is `event`, `timestamp`, `data{call_id, agent_id, duration, status, transcript_url,
recording_url, metadata}` [Docs]. **It has no caller number and no cost.** So:
- the caller number is fetched from `GET /v1/calls/:id` (set `VAANI_API_KEY`) [Docs: endpoint; field name: Check];
- the cost is `duration × PLATFORM_COST_PER_MIN_INR`.

---

## 6 · Cost settings for the dashboard

| `.env` | Value | Source |
|---|---|---|
| `PLATFORM_COST_PER_MIN_INR` | **4.5** | Metered plan, ₹4.5/min, includes speech-to-text, LLM, text-to-speech, analysis and telephony [Docs: vaniagent.com pricing, 2026-10-10]. Use your invoice if your plan differs |
| `TELEPHONY_COST_PER_MIN_INR` | blank | Included above, unless you bring your own Exotel/Twilio/Plivo number |
| `MONTHLY_FIXED_COST_INR` | Hosting + any plan fee | Credits plan ₹4,999/month + ₹2,999 one-time onboarding; Unlimited ₹17,999/month (3-month minimum) [Docs]. Add hosting (~₹700) |

Rough monthly cost at the brief's volume [Likely]: 200 calls × ~4.5 min × ₹4.5 ≈ **₹4,000** of minutes,
plus hosting. That's about ₹20–25 per call before fixed fees. The dashboard computes the real figure.

---

## 7 · ⚠️ One call at a time

VaniAgent's Credits and Unlimited plans list **1 concurrent call** [Docs]. With about 200 calls a month
(~7 a day, ~4–5 min each) two callers will rarely overlap, but sometimes they will. Then the second caller
gets busy or no answer.

**Mitigation (pick one):**
1. **Ring the front desk first in office hours, forward to the bot when unanswered or busy, and route
   everything to the bot after hours** (below). The bot then takes mainly overflow and after-hours calls, so overlaps are rarer.
2. If VaniAgent's busy handling can forward or go to voicemail, point it at the front desk. A missed call
   still reaches the backend as `call.failed` → one callback after 9 am.
3. Ask VaniAgent for the price of 2 concurrent calls (Enterprise).

---

## 8 · Phone number and call forwarding

**Option 1: give out the VaniAgent number** (new number on the website and Instagram). Simplest; old number keeps ringing the desk.

**Option 2 (recommended): forward the studio's existing number to the VaniAgent number.**
On most Indian mobile networks (Jio, Airtel, Vi) these GSM codes work from the studio phone [Likely]:

| Rule | Dial | Use |
|---|---|---|
| Forward when **not answered** | `**61*<VaniAgent number>#` | Office hours: the desk gets first chance |
| Forward when **busy** | `**67*<VaniAgent number>#` | Desk on another call |
| Forward when **unreachable** | `**62*<VaniAgent number>#` | Phone off |
| Forward **everything** | `**21*<VaniAgent number>#` | Turn on at 7 pm, off at 10 am (`##21#`) |
| Cancel all forwarding | `##002#` | Reset |

For a **landline / EPABX / cloud number** (Exotel, Knowlarity, MyOperator), set "forward on no answer
after 20 s" and an after-hours rule in the provider's portal. VaniAgent also supports bringing your own
Twilio / Exotel / Plivo / Telnyx / Vonage account [Docs], which is cleaner than forwarding.

The bot is built to answer at all hours, and the after-hours share is a dashboard metric.

---

## 9 · Mode B: if VaniAgent has no mid-call tools

1. Use the same prompt, but **replace §CONVERSATION FLOW S3–S5** with: *"Collect the facts in the table
   (name, project, area, size, when they need it complete, decision-maker). Do not say whether it's a fit.
   Close with: 'Thank you, I've noted everything. Someone from our studio will call you back on this number.'"*
   Hard rules 1, 3, 4, 7, 9, 10 and 11 still apply.
2. The end-of-call webhook still fires. Every call without a tool decision becomes **one callback** (never 9 pm–9 am)
   carrying the transcript link, so nothing is lost.
3. **What you lose:** live booking, live honest declines, and the rules engine deciding on the call. To get the engine
   back post-call, the transcript has to be turned into facts. That's one extra LLM extraction step in the
   webhook (not built yet: say if you want it).

---

## 10 · Test before going live

Run the 25 calls in `docs/05_red_team_script.md` from two different phones. Pass criteria:
- the bot never says a number about money;
- it never books an unqualified caller (check the dashboard funnel);
- every failure ends in "a person will call you back" plus a callback row;
- every qualified caller produces a Telegram note within a minute.

Then set `MOCK_MODE=0`, restart, and do 3 more real calls.

## Go-live checklist
- [ ] `/health` OK on the public URL
- [ ] `MOCK_MODE=0`, `TOOL_SECRET`, `VAANI_WEBHOOK_SECRET`, `VAANI_API_KEY`, Telegram and (optionally) SMTP set on the host
- [ ] Telegram `setWebhook` done; a test claim tap works
- [ ] Five tools added with the secret header; `evaluate_enquiry` test from the dashboard returns a `say`
- [ ] Webhook "send test" shows on the dashboard
- [ ] Knowledge base uploaded; **pricing.md not uploaded**
- [ ] Call forwarding set; after-hours test call answered by the bot
- [ ] Red-team script passed
