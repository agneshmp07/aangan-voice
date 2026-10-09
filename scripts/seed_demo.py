"""Generate a SYNTHETIC month (September 2026) by pushing fake calls through the real pipeline.

Every number on demo.html comes from the production code paths: the VaniAgent capture
webhook, the rules engine, the callback queue, the Telegram claim race and the metrics API,
run against a throwaway SQLite DB in mock mode. Nothing is hand-typed into the JSON.

    python scripts/seed_demo.py            -> dashboard/demo-data.json

Assumptions (labelled on the page): ~200 calls/month and ~33% after hours (brief), call
length ~4–5 min (September transcripts), ₹4.5/min (VaniAgent metered price) and a ₹4,999/month
plan fee (VaniAgent Credits plan) as the tool's fixed cost. Hosting on Vercel + Supabase free
tiers = ₹0. The mix of outcomes is loosely modelled on the 23 September transcripts.
"""
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TMP = tempfile.mkdtemp()
os.environ.update({
    "AANGAN_NO_DOTENV": "1", "MOCK_MODE": "1", "RUN_SCHEDULER": "0", "DB_PATH": str(Path(TMP) / "demo.db"),
    "PLATFORM_COST_PER_MIN_INR": "4.5", "MONTHLY_FIXED_COST_INR": "4999",
})
for k in ("DATABASE_URL", "TOOL_SECRET", "TELEGRAM_BOT_TOKEN", "VERCEL"):
    os.environ.pop(k, None)

from app import clock, db, settings  # noqa: E402
from app.routers import metrics as metrics_router  # noqa: E402
from app.routers import webhooks  # noqa: E402
from app.services import callbacks, leads  # noqa: E402

settings.reload()
db.init()
R = random.Random(20260930)
IST = clock.IST

# Calls by hour of day (relative weight). Shape: morning ramp, lunch dip, evening peak after work,
# a long tail into the night. Tuned so ~1/3 of calls fall outside 10:00–19:00 (brief).
HOUR_W = [0.3, 0.15, 0.1, 0.05, 0.05, 0.1, 0.4, 1.4, 2.5, 3.6, 6.4, 8.6, 8.0, 6.7, 6.2, 6.9,
          7.4, 7.8, 7.4, 5.9, 5.3, 4.4, 2.6, 1.0]
NAMES = ["Priya", "Rahul", "Sneha", "Amit", "Neha", "Vikram", "Anjali", "Rohan", "Pooja", "Sanjay", "Kavita",
         "Arjun", "Meera", "Nikhil", "Shruti", "Aditya", "Ritu", "Kunal", "Smita", "Girish", "Tanvi", "Siddharth",
         "Divya", "Amol", "Preethi", "Chinmay", "Aarti", "Suresh", "Laleh", "Sunil"]
IN_AREAS = ["Kothrud", "Baner", "Aundh", "Wakad", "Koregaon Park", "Kalyani Nagar", "Viman Nagar", "Hadapsar",
            "Magarpatta", "NIBM", "Kondhwa", "Undri", "Pimple Saudagar", "Hinjewadi", "Ravet", "Kharadi",
            "Bavdhan", "Pimple Nilakh", "Erandwane", "Wanowrie"]
DEADLINES = ["by March", "by February", "by January", "in 4 months", "by end of December", "April 2027"]


def home(**extra):
    bhk = R.choice([2, 2, 3, 3, 3, 4])
    f = dict(caller_name=R.choice(NAMES), language=R.choice(["en", "en", "hi"]), project_category="residential",
             scope=R.choice(["full_home", "full_home", "partial"]), bhk=bhk,
             carpet_area_sqft={2: 900, 3: 1150, 4: 1800}[bhk] + R.randint(-80, 120),
             locality=R.choice(IN_AREAS), deadline_text=R.choice(DEADLINES),
             is_decision_maker=R.choice(["yes", "yes", "unknown"]), asked_price=R.choice(["no", "no", "yes"]))
    if f["scope"] == "partial":
        f["rooms_in_scope"] = R.choice([2, 3])
    f.update(extra)
    return f


SCENARIOS = [  # (weight, label, facts-factory)
    (38, "qualified_home", lambda: home()),
    (5, "qualified_office", lambda: dict(caller_name=R.choice(NAMES), project_category="office", scope="office_fitout",
                                         locality=R.choice(["Baner", "Hinjewadi", "Kharadi", "Viman Nagar"]),
                                         carpet_area_sqft=R.choice([800, 1200, 1800, 2400]), deadline_text="by January",
                                         is_decision_maker="yes")),
    (10, "ask_no_timeline", lambda: home(deadline_text="")),
    (4, "ask_unknown_area", lambda: home(locality=R.choice(["Lohgaon Gaon", "Sus Road township", "Maan"]))),
    (5, "nurture_timeline", lambda: home(deadline_text="in 3 weeks", deadline_flexible="yes", scope="partial", rooms_in_scope=2)),
    (5, "decline_area", lambda: home(locality=R.choice(["Talegaon", "Nashik", "Mumbai", "Lonavala", "Thane"]))),
    (5, "decline_advice", lambda: dict(caller_name=R.choice(NAMES), advice_only="yes", locality=R.choice(IN_AREAS))),
    (3, "decline_budget", lambda: home(scope="partial", rooms_in_scope=2, bhk=1, budget_max_inr=R.choice([100000, 150000, 200000]))),
    (3, "decline_timeline", lambda: home(deadline_text="in 3 weeks", deadline_flexible="no", scope="partial", rooms_in_scope=2)),
    (3, "decline_category", lambda: dict(caller_name=R.choice(NAMES), project_category=R.choice(["restaurant", "gym", "retail shop"]),
                                         locality=R.choice(IN_AREAS))),
    (1, "decline_small_office", lambda: dict(project_category="office", scope="office_fitout", carpet_area_sqft=180,
                                             locality="Baner", is_decision_maker="yes")),
    (6, "escalate", lambda: dict(caller_name=R.choice(NAMES), existing_client="yes", complaint="yes",
                                 existing_client_issue=R.choice(["Designer not replying for 5 days", "Tile delivery delayed",
                                                                 "Carpenter left site midway", "Wants update on handover date"]))),
    (5, "wants_human", lambda: home(deadline_text="", wants_human="yes")),
    (7, "dropped", None),
]


def pick():
    total = sum(w for w, _, _ in SCENARIOS)
    x = R.uniform(0, total)
    for w, label, fn in SCENARIOS:
        x -= w
        if x <= 0:
            return label, fn
    return SCENARIOS[0][1], SCENARIOS[0][2]


def call_time(day: int) -> datetime:
    hour = R.choices(range(24), weights=HOUR_W)[0]
    # Sundays are quieter during the day (front desk closed) but evenings stay busy.
    return datetime(2026, 9, day, hour, R.randint(0, 59), R.randint(0, 59), tzinfo=IST)


def claim_delay(t: datetime) -> datetime | None:
    """Designer claims: fast in office hours; after-hours leads wait for the next morning."""
    if R.random() < 0.04:
        return None  # never claimed (shows up on the dashboard as 'unclaimed')
    if not clock.is_after_hours(t):
        return t + timedelta(minutes=max(2, R.lognormvariate(2.4, 0.6)))  # median ~11 min
    if 19 <= t.hour < 22 and R.random() < 0.45:
        return t + timedelta(minutes=max(3, R.lognormvariate(2.9, 0.5)))  # a designer on their phone
    nxt = (t + timedelta(days=1)) if t.hour >= 10 else t
    return datetime(nxt.year, nxt.month, nxt.day, 10, 0, tzinfo=IST) + timedelta(minutes=R.randint(2, 70))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    phones = [f"+9198{R.randint(10000000, 99999999)}" for _ in range(190)]
    n_calls = 0
    plan = []
    for day in range(1, 31):
        for _ in range(R.choice([5, 6, 6, 7, 7, 8])):
            plan.append(call_time(day))
    plan.sort()
    for i, t in enumerate(plan):
        label, fn = pick()
        phone = R.choice(phones[:150]) if R.random() < 0.08 else phones[i % len(phones)]
        call_id = f"demo-{i:04d}"
        dur = R.uniform(15, 55) if label == "dropped" else max(60.0, R.lognormvariate(5.5, 0.35))
        end = t + timedelta(seconds=dur)
        clock.freeze(t)
        if label == "dropped":
            clock.freeze(end)
            webhooks.process_call_end({"call_id": call_id, "from_number": phone, "started_at": t.isoformat(),
                                       "duration": dur, "status": R.choice(["no-answer", "completed"])})
            n_calls += 1
            continue
        webhooks.record_call({"call_id": call_id, "phone": phone, "started_at": t.isoformat(),
                              "ended_at": end.isoformat(), "duration_s": dur}, raw={"synthetic": True})
        db.execute("UPDATE calls SET synthetic=1 WHERE id=?", call_id)
        clock.freeze(end + timedelta(seconds=R.uniform(5, 40)))
        out = webhooks.process_capture({"call_id": call_id, "phone": phone, "extracted": fn()})
        n_calls += 1
        if out["outcome"] == "QUALIFIED":
            lead = db.row("SELECT id, handoff_sent_at FROM leads WHERE call_id=?", call_id)
            when = claim_delay(clock.parse(lead["handoff_sent_at"]))
            if when:
                clock.freeze(when)
                leads.claim(lead["id"], R.choice(["Asha", "Rohan", "Isha", "Kabir", "Neel", "Tara", "Om"]))
    # Front desk works through callbacks hourly, 9am–9pm (quiet hours enforced by the code).
    for day in range(1, 31):
        for hour in range(9, 21):
            clock.freeze(datetime(2026, 9, day, hour, 5, tzinfo=IST))
            callbacks.dispatch_due()
    db.execute("UPDATE calls SET synthetic=1")
    clock.freeze(datetime(2026, 9, 30, 23, 59, tzinfo=IST))
    m = metrics_router.compute("2026-09-01", "2026-09-30")
    recent = metrics_router.list_leads(limit=12)
    out = {"synthetic": True, "generated_by": "scripts/seed_demo.py", "metrics": m, "recent_leads": recent,
           "assumptions": {"calls": n_calls, "rate_per_min_inr": 4.5, "monthly_fixed_inr": 4999,
                           "note": "September 2026, generated. Volumes from the brief (~200 calls, ~1/3 after hours); "
                                   "outcome mix modelled on the September transcripts; ₹4.5/min and ₹4,999/month from "
                                   "VaniAgent's public pricing (2026-10-10); hosting on free tiers."}}
    dest = ROOT / "dashboard" / "demo-data.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
    v, f = m["volume"], m["funnel"]
    print(f"wrote {dest.relative_to(ROOT)}: {v['calls']} calls, after-hours {m['after_hours']['share_pct']}%, "
          f"funnel {f}, outcomes {m['outcomes']}, cost/call ₹{m['cost']['per_call']}, "
          f"median call→claim {m['time_to_claim']['call_to_claim']['median_min']} min")


if __name__ == "__main__":
    main()
