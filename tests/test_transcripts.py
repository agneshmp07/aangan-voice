"""Replay every September phone call (+ web forms F03, F06, F08) through the rules engine."""
import pytest

from app.rules.engine import ASK, evaluate
from app.rules.price_guard import contains_price
from transcripts import CASES


def replay(case_id):
    case = CASES[case_id]
    facts: dict = {"asked": {}}
    results = []
    for new_facts, _, _ in case["turns"]:
        facts.update(new_facts)
        d = evaluate(facts, today=case["date"])
        results.append(d)
        if d.outcome == ASK:  # the backend counts every question it makes the bot ask
            facts["asked"][d.ask_field] = facts["asked"].get(d.ask_field, 0) + 1
    return results


@pytest.mark.parametrize("case_id", list(CASES))
def test_replay(case_id):
    for i, (d, (_, outcome, detail)) in enumerate(zip(replay(case_id), CASES[case_id]["turns"])):
        assert d.outcome == outcome, f"{case_id} turn {i+1}: {d.outcome} ({d.say_key}) {d.notes}"
        if outcome == ASK:
            assert d.ask_field == detail, f"{case_id} turn {i+1}: asked {d.ask_field}"
        elif detail:
            assert detail in d.reasons, f"{case_id} turn {i+1}: reasons {d.reasons}"
        assert not contains_price(d.say), f"{case_id} would speak a price: {d.say}"


def test_t10_declines_without_a_number():
    d = replay("T10")[-1]
    assert d.say_key == "decline.budget"
    assert not any(ch.isdigit() for ch in d.say)


def test_t16_apologises_and_is_priority():
    d = replay("T16")[0]
    assert d.priority and d.say.startswith("I'm so sorry nobody got back to you")


def test_t02_front_desk_miss_is_caught():
    """'Move in November, design from October' must not be booked without a completion date."""
    d = replay("T02")[0]
    assert d.outcome == ASK and d.say_key == "ask.deadline_exact"


def test_t07_does_not_trust_festival_names():
    d = replay("T07")[1]
    assert d.say_key == "ask.deadline_exact"


def test_f06_far_start_is_qualified_with_note():
    d = replay("F06")[-1]
    assert any("weeks out" in n for n in d.notes)


def test_hindi_callers_get_hindi_and_marathi_falls_back_to_hindi():
    for lang, marker in (("hi", "पुणे"), ("mr", "पुणे")):
        d = evaluate({"language": lang, "scope": "full_home", "project_category": "residential"}, "2026-09-02")
        assert d.say_key == "ask.area" and marker in d.say


def test_summary_table(capsys):
    """Prints the decision table (pytest -s) used in docs and the Lead Register sheet."""
    rows = []
    for cid in CASES:
        res = replay(cid)
        rows.append((cid, res[0].outcome, res[-1].outcome, res[-1].say_key))
    with capsys.disabled():
        print("\n  ID   first-pass  final       spoken line")
        for r in rows:
            print(f"  {r[0]:<4} {r[1]:<11} {r[2]:<11} {r[3]}")
