"""Nikhil's rubric (qualified.md) as a deterministic function.

    evaluate(facts, today) -> Decision(outcome, say, ...)

The LLM collects facts and speaks `say`. It never decides the outcome.
Outcomes: ESCALATE · ASK · QUALIFIED · NURTURE · DECLINE
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime

from . import areas, budget, config as C
from .lines import say as line
from .timeline import parse_when, weeks_between

ESCALATE, ASK, QUALIFIED, NURTURE, DECLINE = "ESCALATE", "ASK", "QUALIFIED", "NURTURE", "DECLINE"
PASS, FAIL, UNCLEAR = "pass", "fail", "unclear"


# --------------------------------------------------------------------------- facts
@dataclass
class Facts:
    """Everything the bot may have learnt. All optional; unknown keys are ignored."""
    language: str = "en"
    # existing client
    existing_client: bool | None = None
    complaint: bool | None = None
    existing_client_issue: str | None = None
    # criterion 1: real project
    project_category: str | None = None   # residential | office | clinic | studio | restaurant | gym | ...
    scope: str | None = None              # full_home | partial | single_room | office_fitout
    wants_execution: bool | None = None
    advice_only: bool | None = None
    service_only: str | None = None       # architecture | structural | decor | furniture_sourcing | vastu
    structural_changes: bool | None = None
    carpet_area_sqft: int | None = None
    rooms_in_scope: int | None = None
    bhk: int | None = None
    # criterion 2: area
    locality: str | None = None
    city: str | None = None
    caller_confirms_pune_pcmc: bool | None = None
    # criterion 3: timeline
    deadline_text: str | None = None
    deadline_date: str | None = None      # ISO, if the caller gave/confirmed an exact date
    deadline_flexible: bool | None = None
    start_text: str | None = None
    # criterion 4: volunteered budget (never probed)
    budget_max_inr: int | None = None
    # criterion 5: decision maker
    is_decision_maker: bool | None = None
    authorised_by_decision_maker: bool | None = None
    decision_maker_will_attend: bool | None = None
    research_only: bool | None = None
    # passthrough for the designer's handoff note (not used to decide)
    caller_name: str | None = None
    referred_by: str | None = None
    site_status: str | None = None
    extra_notes: str | None = None
    # conversation bookkeeping
    asked: dict = field(default_factory=dict)  # {"deadline": 1, ...}
    asked_price: bool | None = None
    repeat_caller_unanswered: bool | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "Facts":
        """Tolerant: ignores unknown keys, coerces 'yes'/'true'/'1' and numeric strings."""
        d = dict(d or {})
        known = {f.name: f for f in fields(cls)}
        out = {}
        for k, v in d.items():
            k2 = k.strip().lower()
            if k2 not in known or v is None or v == "":
                continue
            t = str(known[k2].type)
            if "bool" in t:
                v = _to_bool(v)
            elif "int" in t:
                v = _to_int(v)
                if v is not None and v <= 0:  # voice platforms send 0 for "not said yet"; no real area/BHK/budget is 0
                    v = None
            elif k2 == "asked":
                v = {str(a): _to_int(b) or 0 for a, b in dict(v).items()} if isinstance(v, dict) else {}
            elif "str" in t:
                v = str(v)
            if v is not None:
                out[k2] = v
        return cls(**out)


def _to_bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1", "haan", "ha", "ho", "hoy", "होय", "हाँ", "हां"):
        return True
    if s in ("false", "no", "n", "0", "nahi", "nahin", "nako", "नाही", "नहीं"):
        return False
    return None


def _to_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).lower().replace(",", "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|lacs|l|crore|cr|k)?", s)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5,
            "crore": 1e7, "cr": 1e7, "k": 1e3}.get(m.group(2) or "", 1)
    return int(n * mult)


# --------------------------------------------------------------------------- decision
@dataclass
class Decision:
    outcome: str
    say: str
    say_key: str
    ask_field: str | None = None
    reasons: list[str] = field(default_factory=list)
    criteria: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    priority: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- criteria
def _is_commercial(f: Facts) -> bool:
    cat = (f.project_category or "").lower()
    return cat in C.COMMERCIAL_ALLOWED or f.scope == "office_fitout" or "commercial" in cat


def _c1_real_project(f: Facts, notes: list) -> tuple[str, str | None]:
    cat = (f.project_category or "").lower().strip()
    if any(x in cat for x in C.EXCLUDED_CATEGORIES):
        return FAIL, "decline.excluded_category"
    svc = (f.service_only or "").lower().strip()
    if svc in C.EXCLUDED_SERVICES:
        return FAIL, C.EXCLUDED_SERVICES[svc]
    if f.advice_only or f.wants_execution is False:
        return FAIL, "decline.advice_only"
    if _is_commercial(f) and f.carpet_area_sqft:
        if f.carpet_area_sqft < C.COMMERCIAL_MIN_SQFT:
            return FAIL, "decline.commercial_small"
        if f.carpet_area_sqft > C.COMMERCIAL_MAX_SQFT * (1 + C.COMMERCIAL_MAX_TOLERANCE):
            return FAIL, "decline.commercial_large"
    if f.structural_changes:
        notes.append("Caller mentioned structural changes: we don't move walls. Designer to clarify.")
    if f.scope == "full_home" and f.bhk == 1:
        notes.append("1BHK full home: services.md says 'Full home: 2BHK onwards'. Not declined; designer to judge.")
    if f.wants_execution or f.scope in ("full_home", "partial", "single_room", "office_fitout"):
        return PASS, None
    return UNCLEAR, "scope"


def _c2_india(f: Facts, notes: list) -> tuple[str, str | None]:
    place = " ".join(p for p in (f.locality, f.city) if p).strip()
    if not place:
        return UNCLEAR, "area_india"
    low = place.lower()
    if any(re.search(rf"(?<!\w){re.escape(m)}(?!\w)", low) for m in C.OUTSIDE_INDIA):
        return FAIL, "decline.area_india"
    if areas.classify(f.locality, f.city)[0] != areas.IN:
        notes.append(f"Site outside Pune/PCMC ({place}): confirm travel and site-visit logistics.")
    return PASS, None


def _c2_area(f: Facts, notes: list) -> tuple[str, str | None]:
    if C.SERVICE_AREA == "india":
        return _c2_india(f, notes)
    status, name = areas.classify(f.locality, f.city)
    if status == areas.IN:
        return PASS, None
    if status == areas.OUT:
        return FAIL, "decline.area"
    if status == areas.UNKNOWN:
        if f.caller_confirms_pune_pcmc is True:
            notes.append(f"Locality '{f.locality}' not on our list; caller says it is in Pune/PCMC.")
            return PASS, None
        if f.caller_confirms_pune_pcmc is False:
            return FAIL, "decline.area"
        return UNCLEAR, "area_unknown"
    return UNCLEAR, "area"


def _c3_timeline(f: Facts, today: date, notes: list) -> tuple[str, str | None]:
    deadline = parse_when(f.deadline_date, today) if f.deadline_date else None
    if not deadline and f.deadline_text:
        deadline = parse_when(f.deadline_text, today)
        if not deadline:
            return UNCLEAR, "deadline_exact"  # e.g. "before Diwali": get a date, don't guess
    if deadline:
        lo, hi = (weeks_between(today, d) for d in deadline)
        if hi < C.MIN_WEEKS_TO_COMPLETION:
            if f.deadline_flexible is True:
                return FAIL, "nurture.timeline"
            if f.deadline_flexible is False:
                return FAIL, "decline.timeline_fixed"
            return UNCLEAR, "deadline_flexible"
        if lo < C.MIN_WEEKS_TO_COMPLETION:
            return UNCLEAR, "deadline_exact"  # "November": the 1st fails, the 30th passes
        if lo < C.TIGHT_WEEKS_TO_COMPLETION:
            notes.append(f"Tight timeline: about {lo:.0f} weeks to the completion date.")
        return PASS, None
    if f.start_text:
        start = parse_when(f.start_text, today)
        if start:
            wk = weeks_between(today, start[0])
            if wk > C.FAR_START_WEEKS:
                notes.append(f"Start is about {wk:.0f} weeks out; design phase can begin now.")
            return PASS, None
        return UNCLEAR, "deadline"
    return UNCLEAR, "deadline"


def _c4_budget(f: Facts, notes: list) -> str | None:
    status, ratio = budget.check(
        f.budget_max_inr, is_commercial=_is_commercial(f), scope=f.scope,
        carpet_area_sqft=f.carpet_area_sqft, rooms_in_scope=f.rooms_in_scope, bhk=f.bhk)
    if status == "pass":
        notes.append("Caller volunteered a budget (see handoff). Aligned enough to forward.")
    elif status is None:
        notes.append("Budget not discussed (qualified.md: treat as qualified).")
    return {"pass": PASS, "fail": FAIL, None: PASS}[status]


def _c5_decision_maker(f: Facts, notes: list) -> str:
    if f.is_decision_maker or f.authorised_by_decision_maker:
        return PASS
    if f.decision_maker_will_attend:
        notes.append("Caller is not the owner; decision-maker(s) will attend the consultation.")
        return PASS
    if f.research_only:
        return FAIL
    notes.append("Decision-maker not confirmed (qualified.md: don't push, note it).")
    return PASS


ASK_KEY = {
    "scope": "ask.scope", "area": "ask.area", "area_unknown": "ask.area_unknown", "area_india": "ask.area_india",
    "deadline": "ask.deadline", "deadline_exact": "ask.deadline_exact",
    "deadline_flexible": "ask.deadline_flexible",
}
# A repeat of the same underlying question counts against the same budget of two asks.
ASK_BUCKET = {"area_unknown": "area", "area_india": "area", "deadline_exact": "deadline"}


# --------------------------------------------------------------------------- evaluate
def evaluate(facts: Facts | dict, today: date | str | None = None) -> Decision:
    f = facts if isinstance(facts, Facts) else Facts.from_dict(facts)
    if isinstance(today, str):
        today = datetime.fromisoformat(today).date()
    today = today or date.today()
    lang = f.language
    notes: list[str] = []

    if f.existing_client:
        key = "escalate.complaint" if (f.complaint is not False) else "escalate.existing"
        return Decision(ESCALATE, line(key, lang), key, reasons=["existing_client"],
                        priority=bool(f.complaint is not False), notes=[n for n in [f.existing_client_issue] if n])

    c1, k1 = _c1_real_project(f, notes)
    c2, k2 = _c2_area(f, notes)
    c3, k3 = _c3_timeline(f, today, notes)
    c4 = _c4_budget(f, notes)
    c5 = _c5_decision_maker(f, notes)
    criteria = {"real_project": c1, "service_area": c2, "timeline": c3, "budget": c4, "decision_maker": c5}
    priority = bool(f.repeat_caller_unanswered)
    if f.asked_price:
        notes.append("Asked about price; deflected per pricing.md. Not a disqualifier.")

    fails = []
    if c1 == FAIL:
        fails.append(("real_project", k1))
    if c2 == FAIL:
        fails.append(("service_area", k2))
    if c3 == FAIL:
        fails.append(("timeline", k3))
    if c4 == FAIL:
        fails.append(("budget", "decline.budget"))
    if c5 == FAIL:
        fails.append(("decision_maker", "decline.decision_maker"))

    if len(fails) >= 2:
        return Decision(DECLINE, line("decline.multiple", lang), "decline.multiple",
                        reasons=[r for r, _ in fails], criteria=criteria, notes=notes)
    if len(fails) == 1:
        reason, key = fails[0]
        outcome = NURTURE if key == "nurture.timeline" else DECLINE
        return Decision(outcome, line(key, lang), key, reasons=[reason], criteria=criteria, notes=notes)

    # No fails. Ask about the first unclear hard criterion (1, then 2, then 3), max twice each.
    unresolved = []
    for status, ask in ((c1, k1), (c2, k2), (c3, k3)):
        if status != UNCLEAR:
            continue
        bucket = ASK_BUCKET.get(ask, ask)
        if f.asked.get(bucket, 0) + (f.asked.get(ask, 0) if ask != bucket else 0) >= C.MAX_ASKS_PER_FIELD:
            unresolved.append(bucket)
            continue
        key = ASK_KEY[ask]
        say_text = line(key, lang)
        if priority and not f.asked:
            say_text = line("apology.missed_followup", lang) + " " + say_text
        return Decision(ASK, say_text, key, ask_field=bucket, criteria=criteria,
                        notes=notes, unresolved=unresolved, priority=priority)

    if "deadline_flexible" in unresolved:
        # Deadline fails unless flexible, and the caller wouldn't say: a human should follow up.
        return Decision(NURTURE, line("nurture.timeline", lang), "nurture.timeline",
                        reasons=["timeline"], criteria=criteria, notes=notes, unresolved=unresolved)
    for u in unresolved:
        notes.append(f"Asked twice, still unclear: {u}. Flagged for the designer.")
    return Decision(QUALIFIED, line("qualified", lang), "qualified", criteria=criteria,
                    notes=notes, unresolved=unresolved, priority=priority)
