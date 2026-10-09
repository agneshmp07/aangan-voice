import hmac

from fastapi import Header, HTTPException, Request

from ..settings import settings


def check_secret(given: str | None) -> bool:
    secrets = [s for s in (settings.tool_secret, settings.cron_secret) if s]
    return any(hmac.compare_digest(given or "", s) for s in secrets)


def require_secret(request: Request, x_aangan_secret: str | None = Header(None),
                   authorization: str | None = Header(None)):
    """If TOOL_SECRET is set, every tool/webhook/cron call must carry it, as any of:
    `X-Aangan-Secret: <secret>`, `Authorization: Bearer <secret>` (Vercel Cron sends
    `Bearer <CRON_SECRET>`), or `?key=<secret>` for platforms that can't set headers."""
    if not settings.tool_secret:
        return
    for given in (x_aangan_secret, (authorization or "").removeprefix("Bearer ").strip(),
                  request.query_params.get("key")):
        if given and check_secret(given):
            return
    raise HTTPException(status_code=401, detail="bad secret")
