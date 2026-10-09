"""Fault injection for the failure-mode tests and the red-team script.

Every external dependency calls faults.check("<name>") first. In production FAULTS is empty
and this is a dict lookup. Set e.g. FAULTS["calendar"] = "hang" to prove the 4-second rule.
Names: calendar, telegram, email, sheets, db, engine, outbound.
"""
import time

FAULTS: dict[str, str] = {}


class InjectedFault(RuntimeError):
    pass


def check(name: str):
    mode = FAULTS.get(name)
    if not mode:
        return
    if mode == "hang":
        time.sleep(30)
    if mode.startswith("slow:"):
        time.sleep(float(mode.split(":", 1)[1]))
        return
    raise InjectedFault(f"injected failure in {name}")
