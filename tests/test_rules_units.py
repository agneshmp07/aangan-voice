"""Unit tests: the rules come from the seed files, guardrails hold, price guard is tight."""
import re
from datetime import date

import pytest

from app.rules import areas, config as C
from app.rules.engine import ASK, DECLINE, NURTURE, QUALIFIED, evaluate
from app.rules.lines import LANGS, LINES, say
from app.rules.price_guard import contains_price, price_hits
from app.rules.timeline import parse_when
from conftest import SEED

TODAY = "2026-10-09"
GOOD = dict(project_category="residential", scope="full_home", locality="Baner", bhk=2,
            deadline_text="by April", is_decision_maker=True)


# ---------------------------------------------------------------- seed files → code
def test_every_services_md_locality_is_in_area():
    text = (SEED / "services.md").read_text(encoding="utf8")
    block = text.split("## Service area", 1)[1].split("##", 1)[0]
    named = re.findall(r"\(([^)]*)\)", block)
    places = [p.strip() for grp in named for p in grp.split(",")]
    places = [re.sub(r"^and\s+", "", p) for p in places if p and "adjoining" not in p]
    assert len(places) >= 20
    for p in places:
        assert areas.classify(p)[0] == areas.IN, p


@pytest.mark.parametrize("place", ["Talegaon", "Lonavala", "Nashik", "Mumbai", "Talegaon Dabhade, near Pune",
                                   "Nanded", "Thane"])
def test_excluded_places_are_out(place):
    assert areas.classify(place)[0] == areas.OUT


def test_nanded_city_is_pune_not_nanded():
    assert areas.classify("Nanded City area (Pune)")[0] == areas.IN


def test_unknown_place_is_asked_not_declined():
    d = evaluate({**GOOD, "locality": "Some New Township"}, TODAY)
    assert d.outcome == ASK and d.say_key == "ask.area_unknown"
    d = evaluate({**GOOD, "locality": "Some New Township", "caller_confirms_pune_pcmc": True}, TODAY)
    assert d.outcome == QUALIFIED


def test_devanagari_locality():
    assert areas.classify("कोथरूड")[0] == areas.IN
    assert areas.classify("नाशिक")[0] == areas.OUT


def test_pricing_floor_constants_match_pricing_md():
    text = (SEED / "pricing.md").read_text(encoding="utf8")
    assert f"₹{C.RES_LOW_PER_SQFT:,}" in text.split("Standard specification")[1].split("\n")[0]
    assert f"₹{C.COM_LOW_PER_SQFT:,}" in text.split("Basic fitout")[1].split("\n")[0]
    assert "₹3.5 lakh" in text and C.SINGLE_ROOM_LOW == 350_000


def test_commercial_range_matches_services_md():
    text = (SEED / "services.md").read_text(encoding="utf8")
    assert f"{C.COMMERCIAL_MAX_SQFT:,} sq ft" in text


def test_excluded_categories_match_services_md():
    text = (SEED / "services.md").read_text(encoding="utf8").lower()
    for word in ("restaurant", "hotel", "retail", "gym"):
        assert word in text and any(word in c for c in C.EXCLUDED_CATEGORIES)


# ---------------------------------------------------------------- criteria
def test_budget_not_mentioned_is_qualified():
    assert evaluate(GOOD, TODAY).outcome == QUALIFIED


def test_budget_borderline_is_not_flagged():
    # 2 rooms, budget at ~70% of the floor (F08-style) → pass
    d = evaluate({**GOOD, "scope": "partial", "rooms_in_scope": 2, "budget_max_inr": 500000}, TODAY)
    assert d.outcome == QUALIFIED


def test_two_fails_use_rubric_line():
    d = evaluate({**GOOD, "locality": "Mumbai", "budget_max_inr": 100000}, TODAY)
    assert d.outcome == DECLINE and d.say_key == "decline.multiple"
    assert set(d.reasons) == {"service_area", "budget"}


def test_research_only_alone_declines():
    d = evaluate({**GOOD, "is_decision_maker": False, "research_only": True}, TODAY)
    assert d.outcome == DECLINE and d.reasons == ["decision_maker"]


@pytest.mark.parametrize("svc,key", [("vastu", "decline.vastu_only"), ("furniture_sourcing", "decline.furniture_only"),
                                     ("structural", "decline.architecture"), ("decor", "decline.advice_only")])
def test_scope_exclusions(svc, key):
    d = evaluate({**GOOD, "service_only": svc}, TODAY)
    assert d.outcome == DECLINE and d.say_key == key


def test_commercial_size_range():
    base = dict(GOOD, project_category="office", scope="office_fitout")
    assert evaluate({**base, "carpet_area_sqft": 499}, TODAY).say_key == "decline.commercial_small"
    assert evaluate({**base, "carpet_area_sqft": 500}, TODAY).outcome == QUALIFIED
    assert evaluate({**base, "carpet_area_sqft": 3300}, TODAY).outcome == QUALIFIED
    assert evaluate({**base, "carpet_area_sqft": 5000}, TODAY).say_key == "decline.commercial_large"


def test_residential_has_no_size_cap():
    assert evaluate({**GOOD, "carpet_area_sqft": 9000}, TODAY).outcome == QUALIFIED


def test_rented_apartment_is_fine():
    assert evaluate({**GOOD, "site_status": "rented"}, TODAY).outcome == QUALIFIED


# ---------------------------------------------------------------- timeline maths
def test_timeline_boundary():
    # 10 weeks from 2026-10-09 is 2026-12-18
    assert evaluate({**GOOD, "deadline_date": "2026-12-18"}, TODAY).outcome == QUALIFIED
    d = evaluate({**GOOD, "deadline_date": "2026-12-17", "deadline_flexible": False}, TODAY)
    assert d.outcome == DECLINE
    d = evaluate({**GOOD, "deadline_date": "2026-12-17", "deadline_flexible": True}, TODAY)
    assert d.outcome == NURTURE


def test_tight_timeline_is_noted():
    d = evaluate({**GOOD, "deadline_date": "2026-12-21"}, TODAY)
    assert d.outcome == QUALIFIED and any("Tight" in n for n in d.notes)


@pytest.mark.parametrize("text,lo,hi", [
    ("by March", date(2027, 3, 1), date(2027, 3, 31)),
    ("end of November", date(2026, 11, 21), date(2026, 11, 30)),
    ("February 2027", date(2027, 2, 1), date(2027, 2, 28)),
    ("3 weeks", date(2026, 10, 30), date(2026, 10, 30)),
    ("3-4 months", date(2027, 1, 8), date(2027, 2, 8)),
    ("2026-12-25", date(2026, 12, 25), date(2026, 12, 25)),
    ("नोव्हेंबर", date(2026, 11, 1), date(2026, 11, 30)),
])
def test_parse_when(text, lo, hi):
    assert parse_when(text, date(2026, 10, 9)) == (lo, hi)


def test_festival_names_are_not_parsed():
    assert parse_when("before Diwali", date(2026, 10, 9)) is None


# ---------------------------------------------------------------- guardrails
def test_same_question_at_most_twice_then_flagged():
    facts = {k: v for k, v in GOOD.items() if k != "deadline_text"}
    d1 = evaluate({**facts, "asked": {}}, TODAY)
    d2 = evaluate({**facts, "asked": {"deadline": 1}}, TODAY)
    d3 = evaluate({**facts, "asked": {"deadline": 2}}, TODAY)
    assert d1.outcome == d2.outcome == ASK and d1.ask_field == "deadline"
    assert d3.outcome == QUALIFIED and "deadline" in d3.unresolved
    assert any("Asked twice" in n for n in d3.notes)


def test_existing_client_always_escalates_even_with_bad_facts():
    d = evaluate({"existing_client": True, "complaint": True, "locality": "Mumbai"}, TODAY)
    assert d.outcome == "ESCALATE" and d.priority


def test_tolerant_fact_parsing():
    d = evaluate({**GOOD, "is_decision_maker": "yes", "bhk": "2", "budget_max_inr": "1.5 lakh",
                  "scope": "partial", "rooms_in_scope": "2", "UNKNOWN_FIELD": 1}, TODAY)
    assert d.outcome == DECLINE and d.reasons == ["budget"]


# ---------------------------------------------------------------- price guard
def test_no_approved_line_contains_a_price():
    for key, by_lang in LINES.items():
        for lang in LANGS:
            text = by_lang[lang]
            assert not contains_price(text), f"{key}/{lang}: {price_hits(text)}"


def test_every_line_exists_in_all_three_languages():
    for key, by_lang in LINES.items():
        assert set(by_lang) == set(LANGS), key


@pytest.mark.parametrize("bad", [
    "It'll cost around 18 lakh.", "Our rates start at 1,800 per sq ft.", "Rs 2400/sqft for premium",
    "For a 2BHK it's typically fifteen to twenty lakhs", "₹3.5L for a room", "around 20L all in",
    "about 1800 per square foot", "the cost is 9 to 12", "इसकी कीमत 18 लाख होगी", "दोन लाख रुपये",
    "2400 रुपये प्रति वर्ग फुट", "ek lakh se zyada", "starts at 3500", "budget of 5 lakh is fine",
    "It's 2,000 INR psf", "price range 18 to 24",
])
def test_price_guard_catches(bad):
    assert contains_price(bad)


@pytest.mark.parametrize("ok", [
    "Thursday 15 October at 11am works.", "A redesign takes at least two to three months.",
    "Your 3BHK in Kothrud, about 1,400 square feet.", "I have 10:30 or 4 pm on Saturday.",
    "Let me arrange a call at 11.", "Pricing depends on the site, the materials you choose, and the scope.",
])
def test_price_guard_allows(ok):
    assert not contains_price(ok), price_hits(ok)


def test_say_refuses_to_format_a_price_into_a_line():
    out = say("booking.confirmed", "en", slot="Monday, cost 18 lakh")
    assert out == LINES["fallback.callback"]["en"]
