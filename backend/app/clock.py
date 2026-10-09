"""Time in IST (fixed +05:30, India has no DST, so no tz database needed) and quiet-hours maths."""
from datetime import datetime, time, timedelta, timezone

from .settings import settings

IST = timezone(timedelta(hours=5, minutes=30), "IST")
_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now(IST)


def freeze(dt: datetime | None):
    """Tests and the demo seeder pin the clock."""
    global _frozen
    _frozen = dt.astimezone(IST) if dt and dt.tzinfo else (dt.replace(tzinfo=IST) if dt else None)


def parse(ts) -> datetime | None:
    if ts in (None, ""):
        return None
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    else:
        s = str(ts).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(IST).isoformat(timespec="seconds") if dt else None


def in_quiet_hours(dt: datetime) -> bool:
    h = dt.astimezone(IST).hour
    return h >= settings.quiet_start_hour or h < settings.quiet_end_hour


def next_allowed_callback(dt: datetime) -> datetime:
    """Push a time out of 9pm–9am to the next 9:00am."""
    dt = dt.astimezone(IST)
    if not in_quiet_hours(dt):
        return dt
    day = dt.date() if dt.hour < settings.quiet_end_hour else dt.date() + timedelta(days=1)
    return datetime.combine(day, time(settings.quiet_end_hour, 0), tzinfo=IST)


def is_after_hours(dt: datetime) -> bool:
    dt = dt.astimezone(IST)
    if dt.weekday() not in settings.working_days:
        return True
    return not (settings.office_open_hour <= dt.hour < settings.office_close_hour)
