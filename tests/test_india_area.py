"""Owner decision 2026-10-10: projects anywhere in India; only sites abroad are declined."""
import pytest

from app.rules.engine import ASK, DECLINE, QUALIFIED, evaluate
from test_rules_units import GOOD, TODAY

pytestmark = pytest.mark.india


@pytest.mark.parametrize("place", ["Nashik", "Mumbai", "Bengaluru, Indiranagar", "Lonavala", "Jaipur"])
def test_any_indian_city_qualifies_with_a_logistics_note(place):
    d = evaluate({**GOOD, "locality": place}, TODAY)
    assert d.outcome == QUALIFIED
    assert any("outside Pune/PCMC" in n for n in d.notes)


def test_pune_site_has_no_logistics_note():
    d = evaluate({**GOOD, "locality": "Baner"}, TODAY)
    assert d.outcome == QUALIFIED and not any("outside Pune/PCMC" in n for n in d.notes)


@pytest.mark.parametrize("place", ["Dubai Marina", "London", "Singapore", "दुबई"])
def test_sites_abroad_are_declined(place):
    d = evaluate({**GOOD, "locality": place}, TODAY)
    assert d.outcome == DECLINE and d.say_key == "decline.area_india"


def test_missing_place_asks_city_and_area():
    d = evaluate({**GOOD, "locality": None, "city": None}, TODAY)
    assert d.outcome == ASK and d.say_key == "ask.area_india"
