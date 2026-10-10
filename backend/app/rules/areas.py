"""Service area (criterion 2). Source: services.md "Service area".

IN       — named in services.md, or a well-known Pune/PCMC locality ("and adjoining areas")
OUT      — named as not served in services.md, or another city
UNKNOWN  — something we can't place → the bot asks "Is that within Pune city or Pimpri-Chinchwad?"
MISSING  — nothing said yet
"""
import re
import unicodedata

IN, OUT, UNKNOWN, MISSING = "in", "out", "unknown", "missing"

# Named verbatim in services.md
SERVICES_MD_PUNE = [
    "kothrud", "baner", "aundh", "wakad", "koregaon park", "kalyani nagar", "viman nagar",
    "hadapsar", "magarpatta", "nibm", "kondhwa", "undri", "shivane", "warje", "erandwane", "deccan",
]
SERVICES_MD_PCMC = [
    "pimpri", "chinchwad", "pimple saudagar", "pimple nilakh", "ravet", "hinjewadi",
]
SERVICES_MD_EXCLUDED = ["talegaon", "lonavala", "nashik", "mumbai"]

# "and adjoining areas": Pune Municipal Corporation / PCMC localities not listed by name.
# CONFIRM with Nikhil; these are geography, not his words.
ADJOINING_IN = [
    "pune", "pcmc", "pimpri chinchwad", "kharadi", "nanded city", "sinhagad road", "dhayari",
    "bavdhan", "pashan", "balewadi", "sus", "mahalunge", "shivajinagar", "camp", "wanowrie",
    "yerawada", "mundhwa", "keshav nagar", "bibwewadi", "katraj", "dhanori", "lohegaon",
    "vishrantwadi", "sadashiv peth", "kasba peth", "swargate", "salunke vihar", "fatima nagar",
    "magarpatta city", "cybercity", "amanora", "karve nagar", "kalyani nagar", "boat club road",
    "model colony", "prabhat road", "bhandarkar road", "law college road", "dahanukar colony",
    "sunderban", "baner road", "aundh road", "pimple gurav", "sangvi", "pimple saudagar",
    "thergaon", "tathawade", "punawale", "akurdi", "nigdi", "pradhikaran", "bhosari", "moshi",
    "chikhali", "dapodi", "kasarwadi", "wagholi", "pirangut", "kharadi road", "hinjawadi",
    "hinjewadi phase 1", "hinjewadi phase 2", "hinjewadi phase 3",
]
# Clearly outside Pune/PCMC
OTHER_CITIES_OUT = [
    "talegaon dabhade", "navi mumbai", "thane", "nagpur", "aurangabad", "sambhajinagar",
    "kolhapur", "satara", "solapur", "nanded", "ahmednagar", "goa", "bangalore", "bengaluru",
    "hyderabad", "delhi", "gurgaon", "noida", "chennai", "kolkata", "lavasa", "khandala",
    "alibaug", "lonavla", "baramati", "shirur", "chakan", "khed", "dehu road",
]
# Devanagari spellings the speech-to-text may hand us
DEVANAGARI = {
    "पुणे": "pune", "पुणा": "pune", "कोथरूड": "kothrud", "बाणेर": "baner", "औंध": "aundh",
    "वाकड": "wakad", "हडपसर": "hadapsar", "पिंपरी": "pimpri", "चिंचवड": "chinchwad",
    "हिंजवडी": "hinjewadi", "मुंबई": "mumbai", "नाशिक": "nashik", "तळेगाव": "talegaon",
    "तलेगांव": "talegaon", "लोणावळा": "lonavala", "खराडी": "kharadi", "कोंढवा": "kondhwa",
}


# Filled from the admin page (rules/overrides.py); empty by default.
EXTRA_IN: list[str] = []
EXTRA_OUT: list[str] = []


def normalise(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text).strip().lower()
    for dev, latin in DEVANAGARI.items():
        t = t.replace(dev, latin)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _contains(hay: str, needle: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])", hay) is not None


def classify(locality: str | None, city: str | None = None) -> tuple[str, str | None]:
    """Return (status, matched_name). OUT wins over IN ("Talegaon, near Pune" is OUT)."""
    text = normalise(" ".join(x for x in (locality, city) if x))
    if not text:
        return MISSING, None
    # "nanded city" is in Pune; plain "nanded" is a different city. Check longest names first.
    # An admin exclusion beats the built-in list (e.g. Nikhil stops serving an area).
    in_names = sorted((n for n in SERVICES_MD_PUNE + SERVICES_MD_PCMC + ADJOINING_IN + EXTRA_IN if n not in EXTRA_OUT),
                      key=len, reverse=True)
    out_names = sorted(SERVICES_MD_EXCLUDED + OTHER_CITIES_OUT + EXTRA_OUT, key=len, reverse=True)
    stripped = text
    hit_in = None
    for name in in_names:
        if _contains(stripped, name):
            hit_in = hit_in or name
            stripped = re.sub(rf"(?<![a-z]){re.escape(name)}(?![a-z])", " ", stripped)
    for name in out_names:
        if _contains(stripped, name):
            return OUT, name
    if hit_in:
        return IN, hit_in
    return UNKNOWN, None
