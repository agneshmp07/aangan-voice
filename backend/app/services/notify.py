"""Handoff delivery: Telegram first, email as the automatic fallback, outbox always.

Every message is written to the outbox table whatever happens, so nothing is ever lost:
if both channels fail, the dashboard shows it as a failed handoff and the cron retries.
In MOCK_MODE nothing leaves the machine; the outbox row is the "sent" message.
"""
import hashlib
import hmac
import logging
import smtplib
from email.message import EmailMessage

import httpx

from .. import clock, db, faults
from ..settings import settings

log = logging.getLogger("aangan.notify")


def claim_token(lead_id: int) -> str:
    key = (settings.tool_secret or "aangan-dev-secret").encode()
    return hmac.new(key, f"claim:{lead_id}".encode(), hashlib.sha256).hexdigest()[:20]


def _record(channel, recipient, subject, body, ref, status, error=None, external_id=None) -> int:
    return db.insert("outbox", dict(channel=channel, recipient=recipient, subject=subject, body=body,
                                    ref=ref, status=status, error=error, external_id=external_id,
                                    created_at=clock.iso(clock.now())))


# ---------------------------------------------------------------- telegram
def _telegram_api(method: str, payload: dict) -> dict:
    faults.check("telegram")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    r = httpx.post(url, json=payload, timeout=3.0)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method}: {data.get('description')}")
    return data.get("result") or {}


def send_telegram(chat_id: str | None, text: str, ref: str, claim_lead_id: int | None = None) -> bool:
    markup = None
    if claim_lead_id:
        markup = {"inline_keyboard": [[{"text": "✋ I'll take this lead", "callback_data": f"claim:{claim_lead_id}"}]]}
    try:
        if settings.mock_mode:
            faults.check("telegram")
            _record("telegram", chat_id or "mock-chat", None, text, ref, "mock_sent",
                    external_id=f"mock-{ref}")
            return True
        if not (settings.telegram_bot_token and chat_id):
            raise RuntimeError("telegram not configured")
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if markup:
            payload["reply_markup"] = markup
        res = _telegram_api("sendMessage", payload)
        _record("telegram", chat_id, None, text, ref, "sent", external_id=str(res.get("message_id")))
        return True
    except Exception as e:  # noqa: BLE001 — any failure means fall back
        log.warning("telegram failed: %s", e)
        _record("telegram", chat_id or "?", None, text, ref, "failed", error=str(e)[:500])
        return False


def answer_claim(callback_query_id: str, text: str, chat_id=None, message_id=None, new_text=None):
    """Tell the tapper whether they won; edit the message so everyone sees who took it."""
    if settings.mock_mode or not settings.telegram_bot_token:
        _record("telegram", str(chat_id or "mock-chat"), "claim-answer", text, f"cbq:{callback_query_id}", "mock_sent")
        return
    try:
        _telegram_api("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})
        if new_text and chat_id and message_id:
            _telegram_api("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                              "text": new_text, "parse_mode": "HTML"})
    except Exception as e:  # noqa: BLE001
        log.warning("telegram answer failed: %s", e)


# ---------------------------------------------------------------- email
def send_email(to: str | None, subject: str, body: str, ref: str) -> bool:
    try:
        if settings.mock_mode:
            faults.check("email")
            _record("email", to or "mock@aangan.local", subject, body, ref, "mock_sent")
            return True
        faults.check("email")
        if not (settings.smtp_host and to):
            raise RuntimeError("email not configured")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.email_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password or "")
            s.send_message(msg)
        _record("email", to, subject, body, ref, "sent")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("email failed: %s", e)
        _record("email", to or "?", subject, body, ref, "failed", error=str(e)[:500])
        return False


# ---------------------------------------------------------------- routing
def deliver(audience: str, subject: str, text_html: str, text_plain: str, ref: str,
            claim_lead_id: int | None = None) -> str | None:
    """audience: 'designers' or 'head'. Returns the channel that succeeded, or None."""
    chat = settings.telegram_designers_chat_id if audience == "designers" else settings.telegram_head_chat_id
    to = settings.designers_email if audience == "designers" else settings.head_email
    if send_telegram(chat, text_html, ref, claim_lead_id):
        return "telegram"
    body = text_plain
    if claim_lead_id:
        tok = claim_token(claim_lead_id)
        links = "\n".join(f"  {d}: {settings.public_base_url}/claim/{claim_lead_id}?by={d.replace(' ', '%20')}&t={tok}"
                          for d in settings.designers)
        body += f"\n\nClaim this lead (first click wins):\n{links}\n"
    if send_email(to, subject, body, ref):
        return "email"
    return None
