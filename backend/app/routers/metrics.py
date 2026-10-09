"""Metrics for the dashboard: what the system costs and what it generates.

Cost per call = payload cost if the platform sent one, else minutes × configured rates.
If neither is known, cost is reported as null with `cost.complete: false`, never as zero.
The tool's own running cost (MONTHLY_FIXED_COST_INR: hosting, number, this backend) is
prorated over the period and included in every unit cost.
"""
import statistics
from collections import Counter
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Query

from .. import clock, db
from ..settings import settings

router = APIRouter(prefix="/api", tags=["metrics"])


def _range(start: str | None, end: str | None):
    now = clock.now()
    e = clock.parse(end) or now
    s = clock.parse(start) or (e - timedelta(days=30))
    if start and len(start) == 10:
        s = datetime.combine(s.date(), time(0), tzinfo=clock.IST)
    if end and len(end) == 10:
        e = datetime.combine(e.date(), time(23, 59, 59), tzinfo=clock.IST)
    return s, e


def _pct(n, d):
    return round(100 * n / d, 1) if d else None


def _call_cost(c: dict) -> float | None:
    if c.get("cost_inr") is not None:
        return float(c["cost_inr"])
    rate = None
    if settings.platform_cost_per_min is not None or settings.telephony_cost_per_min is not None:
        rate = (settings.platform_cost_per_min or 0) + (settings.telephony_cost_per_min or 0)
    if rate is None:
        return None
    return round((c.get("duration_s") or 0) / 60 * rate, 2)


def compute(start: str | None = None, end: str | None = None) -> dict:
    s, e = _range(start, end)
    si, ei = clock.iso(s), clock.iso(e)
    calls = db.rows("SELECT * FROM calls WHERE started_at>=? AND started_at<=?", si, ei)
    leads = db.rows("SELECT l.*, c.started_at AS call_started FROM leads l LEFT JOIN calls c ON c.id=l.call_id "
                    "WHERE COALESCE(c.started_at, l.created_at)>=? AND COALESCE(c.started_at, l.created_at)<=?", si, ei)
    callbacks = db.rows("SELECT * FROM callbacks WHERE created_at>=? AND created_at<=?", si, ei)
    tool_events = db.rows("SELECT * FROM events WHERE type='tool' AND ts>=? AND ts<=?", si, ei)
    synthetic = any(c.get("synthetic") for c in calls)

    # -------- volume & timing
    by_hour, by_hour_q, by_weekday, by_day = [0] * 24, [0] * 24, [0] * 7, Counter()
    after = 0
    for c in calls:
        t = clock.parse(c["started_at"])
        by_hour[t.hour] += 1
        by_weekday[t.weekday()] += 1
        by_day[t.date().isoformat()] += 1
        after += clock.is_after_hours(t)
    for l in leads:
        if l["outcome"] == "QUALIFIED":
            by_hour_q[clock.parse(l["call_started"] or l["created_at"]).hour] += 1
    minutes = sum((c.get("duration_s") or 0) for c in calls) / 60

    # -------- funnel & outcomes
    answered = [c for c in calls if not c.get("missed")]
    outcomes = Counter(l["outcome"] or "NO_DECISION" for l in leads)
    enquiries = [l for l in leads if l["outcome"] not in (None, "ESCALATE")]
    qualified = [l for l in leads if l["outcome"] == "QUALIFIED"]
    booked = [l for l in qualified if l["booking_id"]]
    handed = [l for l in qualified if l["handoff_sent_at"]]
    claimed = [l for l in qualified if l["claimed_at"]]
    reasons = Counter(r for l in leads if l["outcome"] in ("DECLINE", "NURTURE")
                      for r in db.unj(l["reasons"], []))
    price_askers = [l for l in leads if l["asked_price"]]
    price_booked = [l for l in price_askers if l["booking_id"]]

    # -------- designer time to claim
    ttc, call_to_claim = [], []
    for l in claimed:
        sent, got = clock.parse(l["handoff_sent_at"]), clock.parse(l["claimed_at"])
        if sent and got:
            ttc.append((got - sent).total_seconds() / 60)
        st = clock.parse(l["call_started"] or l["created_at"])
        if st and got:
            call_to_claim.append((got - st).total_seconds() / 60)

    def dist(xs):
        if not xs:
            return {"n": 0, "median_min": None, "p90_min": None, "within_60_min_pct": None}
        xs = sorted(xs)
        return {"n": len(xs), "median_min": round(statistics.median(xs), 1),
                "p90_min": round(xs[min(len(xs) - 1, int(0.9 * len(xs)))], 1),
                "within_60_min_pct": _pct(sum(x <= 60 for x in xs), len(xs))}

    # -------- cost
    per_call = [_call_cost(c) for c in calls]
    known = [x for x in per_call if x is not None]
    complete = len(known) == len(per_call)
    days = max((e - s).total_seconds() / 86400, 1 / 24)
    fixed = None if settings.monthly_fixed_cost is None else round(settings.monthly_fixed_cost * days / 30, 2)
    variable = round(sum(known), 2) if known else (0.0 if not calls else None)
    total = None if (variable is None or not complete) else round(variable + (fixed or 0), 2)

    def unit(n):
        return round(total / n, 2) if (total is not None and n) else None

    # -------- reliability
    lat = sorted(ev["latency_ms"] for ev in tool_events if ev["latency_ms"] is not None)
    fails = Counter(ev["tool"] for ev in tool_events if not ev["ok"])

    return {
        "period": {"start": si, "end": ei, "days": round(days, 1)},
        "synthetic": synthetic,
        "volume": {"calls": len(calls), "answered": len(answered), "missed": len(calls) - len(answered),
                   "unique_callers": len({c["phone"] for c in calls if c["phone"]}),
                   "minutes": round(minutes, 1),
                   "avg_call_min": round(minutes / len(calls), 2) if calls else None},
        "after_hours": {"calls": after, "share_pct": _pct(after, len(calls)),
                        "office_hours": f"{settings.office_open_hour}:00–{settings.office_close_hour}:00",
                        "qualified_after_hours": sum(clock.is_after_hours(clock.parse(l["call_started"] or l["created_at"]))
                                                     for l in qualified)},
        "by_hour": by_hour, "qualified_by_hour": by_hour_q, "by_weekday": by_weekday,
        "by_day": dict(sorted(by_day.items())),
        "funnel": {"calls": len(calls), "answered": len(answered), "enquiries": len(enquiries),
                   "qualified": len(qualified), "booked": len(booked), "handed_to_designer": len(handed),
                   "claimed": len(claimed)},
        "outcomes": dict(outcomes),
        "decline_reasons": dict(reasons.most_common()),
        "escalations": outcomes.get("ESCALATE", 0),
        "price_question": {"asked": len(price_askers), "booked": len(price_booked),
                           "booked_pct": _pct(len(price_booked), len(price_askers))},
        "time_to_claim": {"handoff_to_claim": dist(ttc), "call_to_claim": dist(call_to_claim),
                          "unclaimed": len(handed) - len([l for l in handed if l["claimed_at"]])},
        "callbacks": dict(Counter(cb["status"] for cb in callbacks)),
        "cost": {"currency": "INR", "complete": complete, "calls_with_known_cost": len(known),
                 "rate_per_min": None if settings.platform_cost_per_min is None and settings.telephony_cost_per_min is None
                 else (settings.platform_cost_per_min or 0) + (settings.telephony_cost_per_min or 0),
                 "variable": variable, "fixed_prorated": fixed, "total": total,
                 "per_call": unit(len(calls)), "per_qualified_lead": unit(len(qualified)),
                 "per_booked_consultation": unit(len(booked)),
                 "note": None if complete else "Set PLATFORM_COST_PER_MIN_INR (or send cost in the call-ended payload) to price every call."},
        "reliability": {"tool_calls": len(tool_events), "failures": dict(fails),
                        "p95_latency_ms": lat[int(0.95 * (len(lat) - 1))] if lat else None},
    }


@router.get("/metrics")
def metrics(start: str | None = Query(None), end: str | None = Query(None)):
    return compute(start, end)


@router.get("/leads")
def list_leads(limit: int = 100):
    out = []
    for l in db.rows("SELECT * FROM leads ORDER BY id DESC LIMIT ?", limit):
        f = db.unj(l["facts"], {})
        out.append({"id": l["id"], "created_at": l["created_at"], "name": f.get("caller_name"),
                    "area": f.get("locality"), "outcome": l["outcome"], "reasons": db.unj(l["reasons"], []),
                    "booked": bool(l["booking_id"]), "claimed_by": l["claimed_by"], "priority": bool(l["priority"])})
    return out
