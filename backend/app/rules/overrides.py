"""Rules Nikhil can change himself (admin page), stored in the rule_overrides table.

Only a whitelist of knobs, each with hard limits, so a typo can't break the rubric:
the code defaults in config.py/areas.py stay the source of truth when nothing is overridden.
"""
import json
import time

from . import areas, config as C

KNOBS = {
    # key: (config attribute, type, min, max, label)
    "min_weeks_to_completion": ("MIN_WEEKS_TO_COMPLETION", int, 4, 26, "Minimum weeks from today to the completion date"),
    "far_start_weeks": ("FAR_START_WEEKS", int, 4, 52, "Flag starts further out than this many weeks (never declined)"),
    "commercial_min_sqft": ("COMMERCIAL_MIN_SQFT", int, 100, 3000, "Smallest commercial space we take (sq ft)"),
    "commercial_max_sqft": ("COMMERCIAL_MAX_SQFT", int, 1000, 20000, "Largest commercial space we take (sq ft)"),
    "budget_clearly_below_ratio": ("BUDGET_CLEARLY_BELOW_RATIO", float, 0.2, 0.9,
                                   "Decline only if a volunteered budget is below this share of the cheapest plausible cost"),
}
LIST_KNOBS = {
    "extra_in_areas": "Extra localities we serve (comma separated)",
    "extra_out_areas": "Extra places we do not serve (comma separated)",
}
DEFAULTS = {k: getattr(C, attr) for k, (attr, *_rest) in KNOBS.items()}
_cache = {"at": 0.0, "values": {}}


def validate(key: str, raw) -> object:
    if key in KNOBS:
        attr, typ, lo, hi, _ = KNOBS[key]
        val = typ(raw)
        if not lo <= val <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}")
        return val
    if key in LIST_KNOBS:
        items = [x.strip().lower() for x in (raw if isinstance(raw, list) else str(raw).split(",")) if x.strip()]
        return sorted(set(items))[:200]
    raise ValueError(f"unknown rule {key}")


def apply(values: dict):
    """Set the live config. Missing keys fall back to the code defaults."""
    for key, (attr, *_rest) in KNOBS.items():
        setattr(C, attr, values.get(key, DEFAULTS[key]))
    C.TIGHT_WEEKS_TO_COMPLETION = C.MIN_WEEKS_TO_COMPLETION + 1
    areas.EXTRA_IN = list(values.get("extra_in_areas", []))
    areas.EXTRA_OUT = list(values.get("extra_out_areas", []))


def load(force: bool = False) -> dict:
    """Read overrides from the DB at most once a minute; failures keep the last good values."""
    if not force and time.time() - _cache["at"] < 60:
        return _cache["values"]
    from .. import db  # late import: rules stay importable without the app
    try:
        rows = db.rows("SELECT key, value FROM rule_overrides")
        values = {r["key"]: json.loads(r["value"]) for r in rows if r["key"] in KNOBS or r["key"] in LIST_KNOBS}
    except Exception:  # noqa: BLE001
        values = _cache["values"]
    _cache.update(at=time.time(), values=values)
    apply(values)
    return values


def reset_cache():
    _cache.update(at=0.0, values={})
    apply({})
