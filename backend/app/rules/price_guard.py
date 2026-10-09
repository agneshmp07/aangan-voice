"""contains_price(): the last line of defence for the Cut.

pricing.md: the agent must never say "any specific number, range, or per-sq-ft figure".
Every approved line is tested against this, and the backend runs it on every string a tool
returns for the bot to speak. Errs towards false positives: a blocked harmless line costs
nothing, a spoken price breaks Nikhil's own rule.
"""
import re
import unicodedata

_CURRENCY = [
    r"₹", r"\brs\.?(?=\s|\d|$)", r"\binr\b", r"\brupees?\b", r"\brupaye?\b", r"\brupiya\b",
    r"\blakhs?\b", r"\blacs?\b", r"\bcrores?\b", r"\bcr\b", r"\bpaise\b", r"\bhazaa?r\b",
    r"\bthousand\b",
    # Devanagari: rupee, lakh, crore, thousand (hi + mr)
    r"रुपये", r"रुपए", r"रुपया", r"रु\.", r"लाख", r"करोड़", r"करोड", r"कोटी", r"हज़ार", r"हजार",
]
_RATE = [
    r"per\s*(?:sq(?:uare)?\.?\s*(?:ft|feet|foot)|sqft|sft)", r"/\s*(?:sq\.?\s*ft|sqft|sft)",
    r"psf\b", r"\bper\s+square\b", r"प्रति\s*(?:वर्ग|चौरस)", r"स्क्वे?अर\s*फ़?ु?ट\s*(?:के|का|ला)",
]
# A number next to cost words: "starts at 18", "around 1,800", "costs 9"
_COST_WORDS = r"(?:cost|costs|costing|price|priced|pricing|rate|rates|budget|charge|charges|fee|fees|starts? at|around|approx|approximately|roughly|typically|ballpark|range|kharcha|daam|kimat|kimmat|खर्च|कीमत|किंमत)"
_NUMBER = r"(?:\d[\d,\.]*|[०-९][०-९,\.]*|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|hundred|ek|do|teen|char|paanch|das|bees|pachaas|sau)"
_NUMBER_NEAR_COST = re.compile(
    rf"(?<!\w){_COST_WORDS}\W+(?:\w+\W+){{0,3}}?{_NUMBER}\b|\b{_NUMBER}\W+(?:\w+\W+){{0,2}}?{_COST_WORDS}(?!\w)",
    re.IGNORECASE,
)
# Common "k"/"L" shorthand: "18k", "3.5L", "20 L"
_SHORTHAND = re.compile(r"\b\d+(?:\.\d+)?\s*(?:k|l)\b", re.IGNORECASE)

_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _CURRENCY + _RATE]


def contains_price(text: str | None) -> bool:
    if not text:
        return False
    t = unicodedata.normalize("NFC", str(text))
    if any(p.search(t) for p in _PATTERNS):
        return True
    if _SHORTHAND.search(t):
        return True
    return bool(_NUMBER_NEAR_COST.search(t))


def price_hits(text: str) -> list[str]:
    """For debugging/tests: which fragments tripped the guard."""
    t = unicodedata.normalize("NFC", str(text))
    hits = [m.group(0) for p in _PATTERNS for m in p.finditer(t)]
    hits += [m.group(0) for m in _SHORTHAND.finditer(t)]
    hits += [m.group(0) for m in _NUMBER_NEAR_COST.finditer(t)]
    return hits
