"""Criterion 4: catch an obvious budget misalignment the caller VOLUNTEERED.

qualified.md: "Don't quote. Don't probe." This module only ever returns pass / fail / None.
It never produces text, so no number can leak into speech from here.
"""
from . import config as C

# Rough carpet areas, used only when the caller gave a BHK but no area. CONFIRM: my estimates.
BHK_DEFAULT_SQFT = {1: 450, 2: 850, 3: 1100, 4: 1700, 5: 2400}


def cheapest_plausible_cost(*, is_commercial: bool, scope: str | None, carpet_area_sqft: int | None,
                            rooms_in_scope: int | None, bhk: int | None) -> int | None:
    """Lowest cost any project of the described scope could have, per pricing.md low ends."""
    estimates = []
    if is_commercial:
        if carpet_area_sqft:
            estimates.append(carpet_area_sqft * C.COM_LOW_PER_SQFT)
    else:
        if rooms_in_scope:
            estimates.append(rooms_in_scope * C.SINGLE_ROOM_LOW)
        if scope == "single_room":
            estimates.append(C.SINGLE_ROOM_LOW)
        if scope == "full_home":
            area = carpet_area_sqft or BHK_DEFAULT_SQFT.get(bhk or 0)
            if area:
                estimates.append(area * C.RES_LOW_PER_SQFT)
    return min(estimates) if estimates else None


def check(budget_max_inr: int | None, **scope) -> tuple[str | None, float | None]:
    """Return (status, ratio). status: None = not mentioned (treated as pass), 'pass', 'fail'."""
    if not budget_max_inr:
        return None, None
    floor = cheapest_plausible_cost(**scope)
    if not floor:
        return "pass", None  # can't judge: never fail on a guess
    ratio = budget_max_inr / floor
    return ("fail" if ratio < C.BUDGET_CLEARLY_BELOW_RATIO else "pass"), round(ratio, 2)
