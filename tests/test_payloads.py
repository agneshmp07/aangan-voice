"""The webhook/tool parser must accept the payload shapes common voice platforms use,
because Vaani's exact shape is not documented to us."""
import os

from app.payloads import normalise_call_end, normalise_phone, normalise_tool_call

FACTS = {"locality": "Baner", "scope": "full_home"}


def test_flat():
    n = normalise_tool_call({"call_id": "c1", "caller_phone": "98200 00001", **FACTS})
    assert n["call_id"] == "c1" and n["phone"] == "+919820000001" and n["args"]["locality"] == "Baner"


def test_args_wrapper_and_metadata():
    n = normalise_tool_call({"args": {"facts": FACTS}, "metadata": {"call_id": "c2", "from": "+91 98200 00002"}})
    assert n["call_id"] == "c2" and n["phone"] == "+919820000002" and n["args"]["facts"] == FACTS


def test_openai_style_string_arguments():
    n = normalise_tool_call({"call": {"id": "c3", "customer": {"number": "+919820000003"}},
                             "tool_calls": [{"id": "tc1", "function": {"name": "evaluate_enquiry",
                                                                       "arguments": '{"locality": "Baner"}'}}]})
    assert n["call_id"] == "c3" and n["tool_call_id"] == "tc1" and n["args"]["locality"] == "Baner"
    assert n["phone"] == "+919820000003"


def test_vapi_style_message_toolcalls():
    n = normalise_tool_call({"message": {"call": {"id": "c4"}, "toolCalls": [
        {"id": "tc4", "function": {"arguments": {"locality": "Aundh"}}}]}})
    assert n["call_id"] == "c4" and n["tool_call_id"] == "tc4" and n["args"]["locality"] == "Aundh"


def test_phone_formats():
    assert normalise_phone("09820000001") == "+919820000001"
    assert normalise_phone("+91-98200-00001") == "+919820000001"
    assert normalise_phone(None) is None


def test_call_end_shapes():
    a = normalise_call_end({"call_id": "x", "from_number": "9820000001", "duration": "125", "transcript": "hi"})
    assert a["duration_s"] == 125 and a["phone"] == "+919820000001"
    b = normalise_call_end({"message": {"type": "end-of-call-report", "call": {"id": "y"},
                                        "customer": {"number": "+919820000002"}, "durationMs": 61000,
                                        "endedReason": "customer-ended-call", "summary": "s"}})
    assert b["call_id"] == "y" and b["duration_s"] == 61 and b["ended_reason"] == "customer-ended-call"
    c = normalise_call_end({"event": "call_ended", "data": {"conversation_id": "z", "status": "no-answer",
                                                             "caller": "9820000003"}})
    assert c["call_id"] == "z" and c["missed"] is True


def test_env_blob_accepted_under_vaani_key_name(monkeypatch):
    """Vercel: the user pasted the whole .env into a variable named VAANI_KEY (2026-10-10)."""
    from app import settings as m
    for k in ("DATABASE_URL", "VAANI_API_KEY", "MOCK_MODE", "vercel_env"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("VAANI_KEY", "DATABASE_URL=postgres://u:p@h/db\nVAANI_API_KEY=abc123\nMOCK_MODE=0")
    m._load_dotenv()
    assert os.environ["DATABASE_URL"].startswith("postgres://") and os.environ["VAANI_API_KEY"] == "abc123"
    monkeypatch.delenv("VAANI_API_KEY")
    monkeypatch.setenv("VAANI_KEY", "plainkey_123")
    m._load_dotenv()
    assert os.environ["VAANI_API_KEY"] == "plainkey_123"
