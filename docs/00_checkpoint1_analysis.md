# Checkpoint 1: Seed-data analysis (working notes)

Sources read: `MESA_Case 03_Problem Statement.pdf`, `seed/Case 03 Seed Data/{services,qualified,pricing}.md`,
`Aangan_Sep 2026_Enquiries.pdf` (20 phone, 10 WhatsApp, 10 web form = 40).
Vaani invite: row for agnesh_mp@pg27.mesaschool.co found (code kept out of the repo).

Decision vocabulary: **ESCALATE** (existing client), **ASK** (criterion 1/2/3 unclear: ask one question),
**QUALIFIED** (book), **NURTURE** (in scope, but the timeline fails *and the caller can move it*),
**DECLINE** (fails a hard criterion).

## 1. Expected outcomes, transcript by transcript

C1 Real project · C2 Area · C3 Timeline · C4 Budget · C5 Decision-maker. ✓ pass, ✗ fail, ? unclear.

| ID | Facts the engine sees | C1 | C2 | C3 | C4 | C5 | Expected | What the front desk actually did / note |
|---|---|---|---|---|---|---|---|---|
| T01 | 3BHK Kothrud, 1,400 sqft, full, done by March, spouse authorised | ✓ | ✓ | ✓ | – | ✓ | **QUALIFIED** | Booked. Referral (Shruti Joshi, Aundh). |
| T02 | 2BHK Wakad, 950, full; "move in November, design from October"; asked for price twice | ✓ | ✓ | **?** | – | ? | **ASK** (completion date), then QUALIFIED | Booked without checking. If they must be finished before a November move-in, design from Oct plus at least 8 weeks of execution doesn't fit. **The front desk approved a timeline that may be impossible.** |
| T03 | Nashik, home office + study | ✓ | ✗ | – | – | ✓ | **DECLINE** (area) | Same. |
| T04 | Ideas for living room, colours/furniture, "just exploring" | ✗ | ? | – | – | – | **DECLINE** (advice only, door left open) | Same. |
| T05 | 4BHK Koregaon Park, 2,400, full, Feb, moved out; friend of Nikhil | ✓ | ✓ | ✓ | – | ? | **QUALIFIED** + VIP flag, site visit | Booked. |
| T06 | Office Baner, 800 sqft bare shell, operational by Dec, founder | ✓ | ✓ | ✓ | – | ✓ | **QUALIFIED** | Booked. |
| T07 | Living + kitchen before Diwali, open to after-Diwali start | ✓ | ? | ✗ (flexible) | – | – | **NURTURE** (honest "can't by Diwali", offer later start; area still to ask) | "Let me think and call back." Nobody follows up, so the lead dies. |
| T08 | Missed call 10:47pm, Nanded City | – | ✓ | – | – | – | **ASK** (the bot answers live) / fallback: **callback at ≥9:00am** | Called back at 10:15am, no answer. Lost. |
| T09 | Existing client, designer Aryan silent for 5 days, wants Nikhil | – | – | – | – | – | **ESCALATE** | Escalated. |
| T10 | 1BHK Kharadi, kitchen + 1 bedroom, volunteers ₹1–1.5L max | ✓ | ✓ | ? | ✗ | ✓ | **DECLINE** (budget; **no number spoken**) | Same. |
| T11 | Rented 2BHK Baner, living + bed + kitchen, no structural, landlord OK, **no timing given** | ✓ | ✓ | **?** | – | ✓ | **ASK** (timeline), then QUALIFIED | Booked without a timeline. Renting is not a disqualifier. |
| T12 | Villa Kalyani Nagar, 5,500 sqft, new, March | ✓ | ✓ | ✓ | – | ✓ | **QUALIFIED** + principal-designer site visit | "Revert by EOD": a promise the bot shouldn't make. |
| T13 | 3BHK Aundh 1,100, kitchen/wardrobes/living, price asked twice, **no timing** | ✓ | ✓ | **?** | – | ? | **ASK** (timeline), then QUALIFIED | Booked. Refused a ballpark and still booked. |
| T14 | Son calling for parents, 3BHK Hadapsar new possession, parents attend and decide, no timing | ✓ | ✓ | **?** | – | ? (represented) | **ASK** (timeline), then QUALIFIED + DM note | Number taken. Per the rubric, C5 unclear means don't push; note it. |
| T15 | 2BHK Undri 875, possession in 6 wks, start design now, spouse authorised | ✓ | ✓ | ✓ | – | ✓ | **QUALIFIED** | Booked. |
| T16 | Repeat caller, 3BHK Viman Nagar, first enquiry dropped, frustrated, scope/timing not restated | ? | ✓ | ? | – | ? | **ASK** (scope) + **PRIORITY** flag | Not an ESCALATE: he isn't a client yet. The real fix is caller-ID lookup. |
| T17 | Dropped at 1:12, rang back 2 min later; 3BHK Pimple Saudagar 1,050, kitchen/wardrobes/living, by March | ✓ | ✓ | ✓ | – | ? | **QUALIFIED**; the queued callback is **cancelled** when the same number calls back | Booked. |
| T18 | Coworking pod, 180 sqft | ✓ | ? | – | – | ✓ | **DECLINE** (below commercial minimum) | Same. |
| T19 | Restaurant, Koregaon Park | ✗ | ✓ | – | – | – | **DECLINE** (excluded category) | Same. |
| T20 | 2BHK Magarpatta 900, full, January start, both owners attend | ✓ | ✓ | ✓ | – | ✓ | **QUALIFIED** | Booked. |
| F03 | Talegaon house 1,400, 3–4 months, ₹15–20L | ✓ | ✗ | ✓ | ✓ | ✓ | **DECLINE** (area) | – |
| F06 | 4BHK NIBM 1,950, partial-plus, start Feb 2027, ₹35–40L firm, 3 studios shortlisted | ✓ | ✓ | ✓* | ✓ | ✓ | **QUALIFIED** + notes (firm cap, aesthetic-fit talk, competitive) | *Fails if criterion 3 is read literally (see contradiction 5). |
| F08 | Wakad living + kitchen, guests in 3 weeks, "3 weeks maximum", ₹4–5L | ✓ | ✓ | ✗ (fixed) | ✓** | ✓ | **DECLINE** (timeline, deadline fixed) | **₹4–5L for two rooms is about 70% of pricing.md's floor. Not "clearly below", so it is not flagged. |

Tally (phone, first pass): QUALIFIED 7 · ASK 6 · NURTURE 1 · DECLINE 5 · ESCALATE 1.
Phone calls booked without asking the timeline: T11, T13, T14 (and T02, where the timeline was unclear). [Certain, from the transcripts]

### Budget-misalignment rule (code only, never spoken)
`floor = carpet_area × residential/commercial low end` for full scope, or `rooms × single-room low end` for partial scope.
Flag only if the caller's **stated maximum < 50% of floor**. Calibrated on the data:
T10 is about 21% (fail), F08 about 71%, F03 about 79%, F10 about 94% (all pass).
Why 50% and not 100%: see contradiction 9. Pricing.md's floor is above the studio's own average project value.

## 2. The Cut

Nikhil wants the system to *"quote our standard per-square-foot pricing."* Check: **pricing.md itself** says "No number from this guide should be quoted… the agent must never say any specific number, range, or per-sq-ft figure." He wrote the rule he's asking us to break.

- **I disagree because:** (a) on the phone, price refusal didn't cost a booking: T02 and T13 both pushed twice for a ballpark, were refused, and booked. (b) The quote can't be accurate. The range runs from ₹1,800 to ₹3,500+ per sqft, the T13 desk says a premium kitchen alone can be 3× a standard one, and sqft means *carpet area of designed space*, which callers routinely confuse with built-up area. (c) A spoken number becomes an anchor the designer then has to fight at consultation.
- **Uncomfortable caveat [Likely]:** the evidence isn't one-sided. W02 and F07 asked for a per-sqft rate and were lost. Both were also left unanswered for days (W02 for 2 days), so delay is the stronger explanation than price refusal. That actually *supports* the build: answer instantly, deflect price, book.
- **Instead:** deflect with pricing.md's exact line, offer to book immediately, and use the low end *inside code only* to catch an obvious misalignment the caller volunteers (T10-style), declining without saying a number.
- **Risk:** some price-shoppers hang up. Mitigation: we measure it. The dashboard tracks the "asked price → booked" rate, so the Cut can be revisited with data and not opinion.

## 3. Contradictions and problems in the brief and seed data

1. **"Arjun" vs Nikhil.** Nine Checks prompt says "the one thing *Arjun* has described wanting". That's a leftover from Case 02. It means Nikhil. [Certain]
2. **The Ask contradicts pricing.md** (the Cut above). [Certain]
3. **Three different minimum timelines.** services.md: "cannot begin execution… ready in under **6 weeks**". qualified.md / T07: "at least **8–10 weeks**". services.md phases: design 3–4 wks + execution 8–16 wks = **11–20 weeks**. The 6-week rule can't be true if the phases are. → Engine uses **10 weeks to the completion deadline** as the hard line (Nikhil's own rubric, upper bound), 10–11 weeks is flagged as "tight" in the note. Configurable. [Certain about the inconsistency; the threshold is my call]
4. **T07's Diwali maths is wrong.** On 8 Sept the desk says "Diwali is about three weeks away". Diwali 2026 is around 8 Nov (about 9 weeks) [Likely], and in 2025 it was about 20 Oct (about 6 weeks). Either way, not 3 weeks. → The bot must ask for a date, never reason from a festival name. With the real date (8–9 weeks) it still fails the 10-week rule, so T07 stays NURTURE.
5. **Criterion 3 is worded two ways.** Literal text: "site must be *available* for execution within 8–10 weeks of the consultation" (an upper bound on start). Its example: "needs it done in 3 weeks" (a lower bound on deadline). Read literally, F06 (start Feb 2027, about 20 weeks out) fails and gets dropped, yet it's a serious ₹35–40L lead comparing 3 studios. → I implement the deadline test as the fail condition. A far-future start becomes **QUALIFIED + note** ("design can start now"), not a decline. Needs Nikhil's sign-off. [Guessing at his intent]
6. **"Fails one → close" vs "two or more fail → decline".** The rubric says both. → Any single hard fail = DECLINE, *except* a timeline fail where the caller can move the date = NURTURE (what the desk did in T07).
7. **No commercial minimum exists in the seed rules.** services.md gives only a ceiling (~3,000 sqft). The 500 sqft floor appears only in the T18 front-desk line. → `COMMERCIAL_MIN_SQFT = 500`, marked "from practice, confirm with Nikhil".
8. **"Full home: 2BHK onwards"** literally excludes a 1BHK full-home redesign, while "partial: 2+ rooms" allows a 1BHK's kitchen + bedroom (T10). Absurd edge. → The engine doesn't decline on BHK count. It flags it in the note only.
9. **Average project value ₹8–14L vs pricing.md.** A standard 950-sqft 2BHK at the *lowest* listed rate is about ₹17L. The studio's real average sits below its own price-guide floor, so either most projects are partial or pricing.md is aspirational. Using pricing.md at face value to filter budgets would decline real customers. Hence the 50% threshold. [Certain about the arithmetic, Guessing about the cause]
10. **Weekdays in the transcripts match 2025, not 2026.** W05 says "20 Sept (Saturday)" and "22 Sept (Monday)", but in 2026 those dates fall on Sunday and Tuesday. T16 ("called Monday… two days", logged on the 19th, note says Friday) only works in 2025. Matters for after-hours and weekend stats in the demo. → The code derives weekdays from the real calendar.
11. **Small ones:** T16 at 10:38am is greeted "Good afternoon". T07 and T20 are answered before 10am, so office hours are softer than stated. The brief's "enquiries/" folder is really one PDF.

## 4. Assumptions of yours I'd challenge

- **"Answered in five minutes" is the wrong target for a voice bot.** It answers in about 2 seconds. The metric that maps to the 4× conversion finding is **qualified-call → designer-claimed time**, so that's what the dashboard leads with.
- **Telegram "first tap wins"** routes leads to the fastest thumb, not the best-fit designer, and puts caller PII on personal phones. I'll still build it as specified, plus a claim timeout that rolls to a fallback. Worth one line in doc 04 on the DPDP Act 2023 (consent and recording disclosure). [Likely]
- **Marathi.** Speech-to-text for Marathi is materially weaker than for Hindi or English [Likely]. A Marathi-only caller who isn't understood after two tries should be routed to a human callback, not looped.
- **"ESCALATE existing clients."** The bot can't verify the claim, so anyone can say they're a client. It's low risk, but escalations should carry "unverified" until matched to the project list.
- **Vaani.** I don't know the Vaani platform's API, webhook payload shapes, tool-timeout limit or per-minute rate. [Guessing at all of it] The backend will accept several payload shapes and read rates from `.env`. If you have Vaani docs or a dashboard link, share it before step 3/4.
