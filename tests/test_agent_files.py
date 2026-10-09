"""The agent files must never carry pricing, and must match the backend."""
import json
import re

from app.rules.price_guard import contains_price, price_hits
from conftest import ROOT, SEED

AGENT = ROOT / "agent"
PRICING_FIGURES = ["1,800", "2,400", "3,500", "1,200", "2,800", "4,000", "3.5 lakh", "8 lakh", "1800", "2400", "3500"]


def spoken_paragraphs(md: str):
    for block in re.split(r"\n\s*\n", re.sub(r"<!--.*?-->", "", md, flags=re.S)):
        if block.strip() and not block.lstrip().startswith("#"):
            yield block.strip()


def test_knowledge_base_has_no_price():
    kb = (AGENT / "knowledge_base.md").read_text(encoding="utf8")
    for para in spoken_paragraphs(kb):
        assert not contains_price(para), (para[:80], price_hits(para))


def test_first_messages_have_no_price_and_disclose_ai_and_recording():
    fm = (AGENT / "first_message.md").read_text(encoding="utf8")
    greetings = [l.lstrip("> ").strip() for l in fm.splitlines() if l.startswith("> ")]
    assert len(greetings) == 3
    for g in greetings:
        assert not contains_price(g)
        assert ("AI" in g) and ("record" in g or "रिकॉर्ड" in g)
        assert len(g) <= 150, f"VaniAgent fixed greeting limit: {len(g)} chars"


def test_no_pricing_md_figure_anywhere_the_agent_can_see():
    assert "₹1,800" in (SEED / "pricing.md").read_text(encoding="utf8")  # the guard is meaningful
    for name in ("system_prompt.md", "system_prompt_compact.md", "system_prompt_vaniagent.md", "knowledge_base.md", "first_message.md", "tools.json"):
        text = (AGENT / name).read_text(encoding="utf8")
        for fig in PRICING_FIGURES:
            assert fig not in text, f"{fig} found in {name}"
        assert "pricing.md" not in text or name != "knowledge_base.md" or "never goes in" in text


def test_tools_json_matches_backend_routes():
    spec = json.loads((AGENT / "tools.json").read_text(encoding="utf8"))
    from app.routers.tools import router
    routes = {r.path for r in router.routes}
    names = [t["function"]["name"] for t in spec["tools"]]
    assert names == ["evaluate_enquiry", "get_consultation_slots", "book_consultation",
                     "escalate_existing_client", "request_human_callback"]
    for t in spec["tools"]:
        assert t["endpoint"] in routes and t["endpoint"].endswith(t["function"]["name"])


def test_tool_fact_fields_exist_in_engine():
    from dataclasses import fields
    from app.rules.engine import Facts
    spec = json.loads((AGENT / "tools.json").read_text(encoding="utf8"))
    props = spec["tools"][0]["function"]["parameters"]["properties"]["facts"]["properties"]
    known = {f.name for f in fields(Facts)}
    assert set(props) <= known, set(props) - known


def test_prompt_quotes_the_exact_price_deflection():
    from app.rules.lines import LINES
    prompt = (AGENT / "system_prompt.md").read_text(encoding="utf8")
    assert LINES["price.deflect"]["en"].replace("; your", ". Your") in prompt
