"""Turn what a caller said about timing into a date window, deterministically.

parse_when("by March", today) -> (date(2027,3,1), date(2027,3,31))
Festival names ("before Diwali") deliberately return None: the bot must ask for a date
rather than trust anyone's festival arithmetic (T07's desk got Diwali wrong by ~6 weeks).
"""
import calendar
import re
from datetime import date, datetime, timedelta

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
# Hindi/Marathi month names in Devanagari and common romanisations
MONTHS.update({
    "जनवरी": 1, "जानेवारी": 1, "फरवरी": 2, "फेब्रुवारी": 2, "मार्च": 3, "अप्रैल": 4, "एप्रिल": 4,
    "मई": 5, "मे": 5, "जून": 6, "जुलाई": 7, "जुलै": 7, "अगस्त": 8, "ऑगस्ट": 8, "सितंबर": 9,
    "सप्टेंबर": 9, "अक्टूबर": 10, "ऑक्टोबर": 10, "नवंबर": 11, "नोव्हेंबर": 11, "दिसंबर": 12,
    "डिसेंबर": 12, "farvari": 2, "navambar": 11, "disambar": 12, "janvari": 1,
})
WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1,
             "couple of": 2, "few": 3}
NOW_WORDS = ("asap", "as soon as possible", "immediately", "right away", "right now", "now",
             "this month", "turant", "jaldi", "lagech", "abhi")

Window = tuple[date, date]


def _month_window(month: int, year: int, part: str | None) -> Window:
    last = calendar.monthrange(year, month)[1]
    if part == "early":
        return date(year, month, 1), date(year, month, 10)
    if part == "mid":
        return date(year, month, 11), date(year, month, 20)
    if part in ("late", "end"):
        return date(year, month, 21), date(year, month, last)
    return date(year, month, 1), date(year, month, last)


def _num(tok: str) -> float | None:
    tok = tok.strip()
    if re.fullmatch(r"\d+(\.\d+)?", tok):
        return float(tok)
    return WORD_NUMS.get(tok)


def parse_when(text: str | None, today: date) -> Window | None:
    if not text:
        return None
    t = str(text).strip().lower()

    # ISO / explicit dates first
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(t.replace(",", ""), fmt).date()
            return d, d
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if m.group(3):
            d = date(y, mo, int(m.group(3)))
            return d, d
        return _month_window(mo, y, None)

    if any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) for w in NOW_WORDS):
        return today, today

    m = re.search(r"\bnext\s+(week|month|year)\b", t)
    if m:
        days = {"week": 7, "month": 30, "year": 365}[m.group(1)]
        start = today + timedelta(days=days)
        return start, start + timedelta(days=min(days, 30))

    # "in 3 weeks", "3-4 months", "six weeks", "a couple of months"
    m = re.search(r"(?<![a-z])(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
                  r"twelve|a|an|couple of|few)\s*(?:(?:-|to|–)\s*(\d+))?\s*(week|month|day)s?", t)
    if m:
        lo = _num(m.group(1))
        hi = float(m.group(2)) if m.group(2) else lo
        unit = {"day": 1, "week": 7, "month": 30.44}[m.group(3)]
        if lo is not None:
            return today + timedelta(days=round(lo * unit)), today + timedelta(days=round(hi * unit))

    # Month names, optional year and part-of-month
    part = None
    if re.search(r"\bearly\b|\bstart of\b|\bbeginning of\b", t):
        part = "early"
    elif re.search(r"\bmid\b|\bmiddle of\b", t):
        part = "mid"
    elif re.search(r"\blate\b|\bend of\b", t):
        part = "end"
    for name, num in sorted(MONTHS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", t):
            ym = re.search(r"(20\d\d)", t)
            if ym:
                year = int(ym.group(1))
            else:
                year = today.year if num >= today.month else today.year + 1
            return _month_window(num, year, part)
    return None


def weeks_between(a: date, b: date) -> float:
    return (b - a).days / 7.0
