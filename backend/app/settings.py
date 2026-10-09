"""All configuration comes from environment variables (see .env.example).

Anything I could not verify about the Vaani platform (payload shapes, per-minute rate,
tool timeout) is a setting, never a hard-coded guess. Costs default to None = "unknown",
and the metrics API reports them as unknown, not as zero.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv():
    if os.environ.get("AANGAN_NO_DOTENV") == "1":  # tests: never read real keys
        return
    p = ROOT / ".env"
    if p.exists():
        for raw in p.read_text(encoding="utf8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _f(name, default=None):
    v = os.environ.get(name)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _b(name, default=False):
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass
class Settings:
    mock_mode: bool = True
    db_path: str = str(ROOT / "data" / "aangan.db")
    database_url: str | None = None         # postgres://… (Supabase pooler) → used instead of SQLite
    serverless: bool = False                # Vercel: no background loop, run follow-ups inline
    cron_secret: str | None = None          # Vercel Cron sends Authorization: Bearer <CRON_SECRET>
    tool_secret: str | None = None          # if set, tools/webhooks require X-Aangan-Secret
    public_base_url: str = "http://localhost:8000"

    # Guardrails
    tool_timeout_s: float = 2.5             # worst case: 0.5 body + 2.5 tool + 0.5 fallback = 3.5s < 4s
    quiet_start_hour: int = 21              # no callbacks 9pm–9am
    quiet_end_hour: int = 9
    callback_delay_min: int = 10            # wait before calling a dropped caller back
    callback_dedupe_hours: int = 24         # one dropped-call callback per number per window
    dropped_call_max_s: int = 90            # shorter than this with no decision = dropped
    claim_timeout_min: int = 30             # unclaimed lead → re-alert studio head by email

    # Office hours (brief: front desk 10am–7pm). Working days Mon–Sat is a guess: CONFIRM.
    office_open_hour: int = 10
    office_close_hour: int = 19
    working_days: list = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    slot_hours: list = field(default_factory=lambda: [11, 15, 17])
    slot_minutes: int = 60
    slots_offered: int = 3

    # Costs (INR). None = unknown. Payload-provided cost always wins over the rate.
    platform_cost_per_min: float | None = None   # Vaani all-in voice rate: UNKNOWN, set from invoice
    telephony_cost_per_min: float | None = None  # if billed separately
    monthly_fixed_cost: float | None = None      # hosting, number rental, the tool itself

    # Handoff
    telegram_bot_token: str | None = None
    telegram_designers_chat_id: str | None = None
    telegram_head_chat_id: str | None = None
    telegram_webhook_secret: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = "aangan-bot@localhost"
    designers_email: str | None = None
    head_email: str | None = None
    designers: list = field(default_factory=list)

    # Google
    google_service_account_file: str | None = None
    google_calendar_id: str | None = None
    google_sheet_id: str | None = None

    # Callbacks: "human" = task to front desk; "vaani_outbound" = POST to an outbound-call URL
    callback_mode: str = "human"
    vaani_outbound_url: str | None = None
    vaani_api_key: str | None = None
    # VaniAgent (api.vaniagent.com) public docs, read 2026-10-10: webhooks are signed with
    # HMAC-SHA256 hex of the body in X-Vaniagent-Signature; REST base https://api.vaniagent.com/v1
    vaani_webhook_secret: str | None = None
    vaani_api_base: str = "https://api.vaniagent.com/v1"


def _abs(p: str) -> str:
    """Relative paths in .env are relative to the project root, not the current directory."""
    q = Path(p)
    return str(q if q.is_absolute() else ROOT / q)


def load() -> Settings:
    _load_dotenv()
    e = os.environ.get
    return Settings(
        mock_mode=_b("MOCK_MODE", True),
        db_path=_abs(e("DB_PATH") or ("/tmp/aangan.db" if e("VERCEL") else "data/aangan.db")),
        database_url=e("DATABASE_URL") or None,
        serverless=bool(e("VERCEL")) or _b("SERVERLESS", False),
        tool_secret=e("TOOL_SECRET") or None,
        cron_secret=e("CRON_SECRET") or None,
        public_base_url=e("PUBLIC_BASE_URL", "http://localhost:8000"),
        tool_timeout_s=_f("TOOL_TIMEOUT_S", 2.5),
        callback_delay_min=int(_f("CALLBACK_DELAY_MIN", 10)),
        callback_dedupe_hours=int(_f("CALLBACK_DEDUPE_HOURS", 24)),
        dropped_call_max_s=int(_f("DROPPED_CALL_MAX_S", 90)),
        claim_timeout_min=int(_f("CLAIM_TIMEOUT_MIN", 30)),
        platform_cost_per_min=_f("PLATFORM_COST_PER_MIN_INR"),
        telephony_cost_per_min=_f("TELEPHONY_COST_PER_MIN_INR"),
        monthly_fixed_cost=_f("MONTHLY_FIXED_COST_INR"),
        telegram_bot_token=e("TELEGRAM_BOT_TOKEN") or None,
        telegram_designers_chat_id=e("TELEGRAM_DESIGNERS_CHAT_ID") or None,
        telegram_head_chat_id=e("TELEGRAM_HEAD_CHAT_ID") or None,
        telegram_webhook_secret=e("TELEGRAM_WEBHOOK_SECRET") or None,
        smtp_host=e("SMTP_HOST") or None,
        smtp_port=int(_f("SMTP_PORT", 587)),
        smtp_user=e("SMTP_USER") or None,
        smtp_password=e("SMTP_PASSWORD") or None,
        email_from=e("EMAIL_FROM", "aangan-bot@localhost"),
        designers_email=e("DESIGNERS_EMAIL") or None,
        head_email=e("HEAD_EMAIL") or None,
        designers=_list("DESIGNERS", "Designer A,Designer B,Designer C"),
        google_service_account_file=e("GOOGLE_SERVICE_ACCOUNT_FILE") or None,
        google_calendar_id=e("GOOGLE_CALENDAR_ID") or None,
        google_sheet_id=e("GOOGLE_SHEET_ID") or None,
        callback_mode=e("CALLBACK_MODE", "human"),
        vaani_outbound_url=e("VAANI_OUTBOUND_URL") or None,
        vaani_api_key=e("VAANI_API_KEY") or None,
        vaani_webhook_secret=e("VAANI_WEBHOOK_SECRET") or None,
        vaani_api_base=e("VAANI_API_BASE", "https://api.vaniagent.com/v1"),
    )


settings = load()


def reload() -> Settings:
    global settings
    new = load()
    settings.__dict__.update(new.__dict__)
    return settings
