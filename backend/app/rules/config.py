"""Business rules as code. Every constant cites the seed file it comes from.

Anything marked CONFIRM is a judgement call made where the seed files contradict
each other (see docs/00_checkpoint1_analysis.md) and should be signed off by Nikhil.
"""

# --- Criterion 3: realistic timeline -------------------------------------------------
# qualified.md: "The site must be available for execution within 8–10 weeks of the
# consultation. If someone needs it done in 3 weeks, we cannot serve them well."
# T07 front desk: "a room redesign with execution takes at least 8-10 weeks".
# services.md says 6 weeks, but its own phases (design 3–4 + execution 8–16) make 6 impossible.
# CONFIRM: we use the upper bound of Nikhil's rubric as the hard line.
MIN_WEEKS_TO_COMPLETION = 10
# services.md: design 3 weeks + execution 8 weeks = 11. Between 10 and 11 → qualified, flagged "tight".
TIGHT_WEEKS_TO_COMPLETION = 11
# A start further out than this is noted for the designer, never declined (CONFIRM, see F06).
FAR_START_WEEKS = 10

# --- Criterion 1: scope -----------------------------------------------------------------
# services.md: "Commercial projects: offices, clinics, studios — up to approximately 3,000 sq ft."
COMMERCIAL_MAX_SQFT = 3000
COMMERCIAL_MAX_TOLERANCE = 0.10          # "approximately" → accept up to 3,300
# CONFIRM: not in services.md or qualified.md; front-desk practice from T18
# ("Our commercial projects are typically 500 sq ft or more").
COMMERCIAL_MIN_SQFT = 500

COMMERCIAL_ALLOWED = {"office", "clinic", "studio"}
# services.md: "Restaurants, hotels, retail stores, gyms: out of scope."
EXCLUDED_CATEGORIES = {
    "restaurant", "cafe", "bar", "hotel", "hospitality", "resort",
    "retail", "shop", "store", "showroom", "gym", "fitness",
}
# services.md "What we don't do"
EXCLUDED_SERVICES = {
    "architecture": "decline.architecture",
    "structural": "decline.architecture",
    "decor": "decline.advice_only",
    "styling": "decline.advice_only",
    "advice": "decline.advice_only",
    "furniture_sourcing": "decline.furniture_only",
    "vastu": "decline.vastu_only",
}

# --- Criterion 4: budget (INTERNAL ONLY — never spoken, never in the knowledge base) -----
# Low ends from pricing.md. tests/test_rules_units.py re-parses pricing.md to keep these honest.
RES_LOW_PER_SQFT = 1800          # "Standard specification ₹1,800 – ₹2,400 per sq ft"
COM_LOW_PER_SQFT = 1200          # "Basic fitout ₹1,200 – ₹1,800 per sq ft"
SINGLE_ROOM_LOW = 350_000        # "Single room redesign (all-in): ₹3.5 lakh – ₹8 lakh"
# qualified.md: flag only "a number that is clearly below what any project of their described
# scope would cost". CONFIRM: "clearly" = below half the cheapest plausible cost. Loose on
# purpose: the studio's average project (₹8–14L, brief) sits below pricing.md's own floor.
BUDGET_CLEARLY_BELOW_RATIO = 0.5

# --- Guardrails -------------------------------------------------------------------------
MAX_ASKS_PER_FIELD = 2           # ask the same question at most twice, then flag for designer
