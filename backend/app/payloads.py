"""Payload normalisation.

I do not know Vaani's exact tool-call or end-of-call payload shape [Guessing]. Rather than
invent field names, these functions search for the values in every common place voice
platforms put them (flat JSON, {args}, {arguments: "json string"}, OpenAI-style tool_calls,
Vapi-style message.toolCalls, Retell-style call{...}). When Vaani's real payload is known,
add its paths here and to tests/test_payloads.py; nothing else changes.
"""
import json
from typing import Any

CALL_ID_KEYS = ("call_id", "callId", "call_sid", "callSid", "session_id", "sessionId",
                "conversation_id", "conversationId", "id")
PHONE_KEYS = ("caller_phone", "callerPhone", "from_number", "fromNumber", "from", "caller",
              "customer_number", "customerNumber", "phone", "phone_number", "phoneNumber", "number", "ani")
TOOL_CALL_ID_KEYS = ("toolCallId", "tool_call_id", "id")


def _maybe_json(v):
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return json.loads(s)
            except ValueError:
                return v
    return v


def _walk(obj: Any, keys: tuple, depth=0):
    """Breadth-first search for the first non-empty value under any of `keys`."""
    if depth > 5:
        return None
    obj = _maybe_json(obj)
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if v not in (None, "", {}, []) and not isinstance(v, (dict, list)):
                return v
        for k in ("call", "customer", "message", "data", "payload", "metadata", "body", "event"):
            if k in obj:
                found = _walk(obj[k], keys, depth + 1)
                if found not in (None, ""):
                    return found
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found = _walk(v, keys, depth + 1)
                if found not in (None, ""):
                    return found
    elif isinstance(obj, list):
        for v in obj:
            found = _walk(v, keys, depth + 1)
            if found not in (None, ""):
                return found
    return None


def _extract_args(body: dict) -> tuple[dict, str | None]:
    """Return (arguments, tool_call_id)."""
    # Vapi-like: message.toolCalls[0].function.arguments / OpenAI-like: tool_calls[0]
    for container in (body, body.get("message") or {}):
        container = _maybe_json(container)
        if not isinstance(container, dict):
            continue
        for key in ("toolCalls", "tool_calls", "toolCallList", "tool_call_list"):
            calls = container.get(key)
            if isinstance(calls, list) and calls:
                tc = calls[0]
                fn = tc.get("function", tc)
                args = _maybe_json(fn.get("arguments") or fn.get("parameters") or {})
                return (args if isinstance(args, dict) else {}), tc.get("id") or tc.get("toolCallId")
        for key in ("tool_call", "toolCall", "function_call", "functionCall"):
            tc = container.get(key)
            if isinstance(tc, dict):
                fn = tc.get("function", tc)
                args = _maybe_json(fn.get("arguments") or fn.get("parameters") or {})
                return (args if isinstance(args, dict) else {}), tc.get("id")
    for key in ("args", "arguments", "parameters", "params", "input", "inputs"):
        if key in body:
            args = _maybe_json(body[key])
            if isinstance(args, dict):
                return args, body.get("toolCallId") or body.get("tool_call_id")
    # Flat: the body itself is the arguments
    return {k: v for k, v in body.items() if k not in ("call", "message", "metadata")}, None


def normalise_tool_call(body: dict | None) -> dict:
    body = body if isinstance(body, dict) else {}
    args, tc_id = _extract_args(body)
    call_id = args.get("call_id") or _walk(body, ("call_id", "callId", "call_sid", "callSid",
                                                  "session_id", "sessionId", "conversation_id"))
    if not call_id:
        msg = body.get("message") if isinstance(body.get("message"), dict) else {}
        for call in (body.get("call"), msg.get("call")):
            if isinstance(call, dict) and call.get("id"):
                call_id = call["id"]
                break
    phone = args.get("caller_phone") or _walk(body, PHONE_KEYS)
    return {"call_id": str(call_id) if call_id else None, "phone": normalise_phone(phone),
            "args": args, "tool_call_id": tc_id}


def normalise_phone(p) -> str | None:
    if not p:
        return None
    digits = "".join(ch for ch in str(p) if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        digits = "91" + digits
    if digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]
    return "+" + digits


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalise_call_end(body: dict | None) -> dict:
    """End-of-call report → our call record. Every field optional."""
    body = body if isinstance(body, dict) else {}
    g = lambda *keys: _walk(body, keys)
    started = g("started_at", "startedAt", "start_time", "startTime", "start_timestamp", "call_start")
    ended = g("ended_at", "endedAt", "end_time", "endTime", "end_timestamp", "call_end")
    duration = _num(g("duration_s", "duration", "durationSeconds", "duration_seconds", "call_duration"))
    duration_ms = _num(g("duration_ms", "durationMs"))
    if duration is None and duration_ms is not None:
        duration = duration_ms / 1000
    cost = _num(g("cost_inr", "costInr", "cost", "total_cost", "totalCost", "call_cost"))
    currency = (g("currency", "cost_currency") or "").upper()
    transcript = g("transcript", "transcription", "transcript_text") or g("transcript_url", "transcriptUrl")
    if transcript is None:
        msgs = _walk_list(body, ("messages", "transcript_object", "transcriptObject"))
        if msgs:
            transcript = "\n".join(f"{m.get('role', '?')}: {m.get('message') or m.get('content') or ''}"
                                   for m in msgs if isinstance(m, dict))
    status = g("status", "call_status", "callStatus")
    reason = g("ended_reason", "endedReason", "end_reason", "disconnection_reason", "disconnectReason",
               "hangup_cause", "hangupCause") or status
    event = str(body.get("event") or body.get("type") or "").lower()
    missed = str(status or "").lower() in ("no-answer", "no_answer", "missed", "busy", "failed", "unanswered")         or event in ("call.failed", "call_failed")
    return {
        "call_id": str(g(*CALL_ID_KEYS) or "") or None,
        "phone": normalise_phone(g(*PHONE_KEYS)),
        "started_at": started, "ended_at": ended, "duration_s": duration,
        "ended_reason": str(reason) if reason else None,
        "language": g("language", "detected_language", "lang"),
        "transcript": transcript if isinstance(transcript, str) else (json.dumps(transcript, ensure_ascii=False) if transcript else None),
        "summary": g("summary", "call_summary", "analysis_summary"),
        "recording_url": g("recording_url", "recordingUrl", "recording", "stereoRecordingUrl"),
        # Only trust a payload cost if it is INR or carries no currency; otherwise fall back to rates.
        "cost_inr": cost if cost is not None and currency in ("", "INR") else None,
        "missed": missed,
        "event": event or None,
    }


def _walk_list(obj, keys, depth=0):
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k in keys:
            if isinstance(obj.get(k), list):
                return obj[k]
        for v in obj.values():
            r = _walk_list(v, keys, depth + 1)
            if r:
                return r
    return None


def tool_response(payload: dict, tool_call_id: str | None) -> dict:
    """Answer in a shape most platforms accept: our flat JSON, plus a results[] envelope
    keyed by toolCallId when the request carried one."""
    out = dict(payload)
    if tool_call_id:
        out["results"] = [{"toolCallId": tool_call_id, "result": json.dumps(payload, ensure_ascii=False)}]
    return out
