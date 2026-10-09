"""The 4-second rule.

Every tool runs inside run_tool(): the work happens in a worker thread with a hard deadline
(TOOL_TIMEOUT_S, default 3.0s). If it raises or overruns, the caller hears
"a person will call you back" and a callback is queued. Slow side effects (Telegram,
Sheets) run after the response has been sent. The returned `say` is price-checked last.
"""
import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse

from . import clock, db, payloads
from .rules.lines import say as line
from .rules.price_guard import contains_price
from .services import callbacks
from .settings import settings

log = logging.getLogger("aangan.guard")
META_KEYS = {"call_id", "caller_phone", "language", "facts", "toolCallId", "tool_call_id"}


def call_id_for(norm: dict) -> str:
    if norm["call_id"]:
        return norm["call_id"]
    # Platform didn't send a call id: one pseudo-call per number per hour.
    return f"anon-{norm['phone'] or 'unknown'}-{clock.now():%Y%m%d%H}"


def _last_resort_log(record: dict):
    try:
        p = Path(settings.db_path).parent / "fallback.log"
        with p.open("a", encoding="utf8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 — nothing left to try
        pass


async def _fallback(tool: str, norm: dict, err: BaseException) -> dict:
    lang = (norm["args"] or {}).get("language")
    reason = "booking_uncertain" if tool == "book_consultation" else f"tool_failed:{tool}"
    try:
        await asyncio.wait_for(asyncio.to_thread(
            callbacks.queue, norm["phone"], reason, norm.get("_call_id"), tool == "book_consultation",
            f"{type(err).__name__}: {str(err)[:200]}"), timeout=0.5)
    except BaseException as e2:  # noqa: BLE001 — DB down too: write to a file and still answer
        _last_resort_log({"ts": clock.iso(clock.now()), "tool": tool, "phone": norm["phone"],
                          "call_id": norm.get("_call_id"), "error": repr(err), "queue_error": repr(e2)})
    return {"ok": False, "error": "temporarily_unavailable", "outcome": None,
            "say": line("fallback.callback", lang), "next_tools": []}


async def run_tool(tool: str, request: Request, background: BackgroundTasks, fn) -> JSONResponse:
    t0 = time.perf_counter()
    try:
        body = await asyncio.wait_for(request.json(), timeout=0.5)
    except Exception:  # noqa: BLE001 — empty/invalid body is still a call we must answer
        body = {}
    norm = payloads.normalise_tool_call(body)
    norm["_call_id"] = call_id_for(norm)
    later: list = []
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fn, norm, later), timeout=settings.tool_timeout_s)
        ok = bool(result.get("ok", True))
    except BaseException as e:  # noqa: BLE001 — includes TimeoutError
        log.warning("%s failed: %r", tool, e)
        result, ok, later = await _fallback(tool, norm, e), False, []
    if contains_price(result.get("say")):
        log.error("%s tried to speak a price; replaced", tool)
        result["say"] = line("fallback.callback", (norm["args"] or {}).get("language"))
    for job in later:
        if settings.serverless:
            _safe(job)  # Vercel may freeze the function right after responding: do it now
        else:
            background.add_task(_safe, job)
    latency = (time.perf_counter() - t0) * 1000
    background.add_task(_safe, lambda: db.insert("events", dict(
        ts=clock.iso(clock.now()), type="tool", call_id=norm["_call_id"], tool=tool,
        latency_ms=round(latency, 1), ok=int(ok), data=result.get("error") or result.get("outcome"))))
    return JSONResponse(payloads.tool_response(result, norm["tool_call_id"]))


def _safe(job):
    try:
        job()
    except Exception as e:  # noqa: BLE001
        log.warning("background job failed: %r", e)
