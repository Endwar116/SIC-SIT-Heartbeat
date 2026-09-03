"""Shared plumbing for PreToolUse-style gates.

Contract (Claude Code hooks; other harnesses can adapt):
  * stdin  : JSON {"tool_name": ..., "tool_input": {...}}
  * exit 0 : allow
  * exit 2 : BLOCK — stderr is shown to the agent as the reason
  * exit 1 : warn only, the action still runs  <-- never use this for policy
Gates must be fast (<500 ms) and must never crash-block on their own bugs:
if we cannot parse the input we allow, log the anomaly, and get out of the way.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

ALLOW, BLOCK = 0, 2


def read_payload():
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def block(reason: str, gate: str):
    sys.stderr.write(f"⛔ {gate}: {reason}\n")
    _record(gate, "blocked", reason)
    sys.exit(BLOCK)


def allow(gate: str = None, note: str = None):
    if gate and note:
        _record(gate, "allowed", note)
    sys.exit(ALLOW)


def _record(gate, verdict, reason):
    """Every gate decision is itself evidence. Append to state/gate_decisions.jsonl."""
    try:
        paths.ensure_dirs()
        with open(paths.STATE / "gate_decisions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "gate": gate, "verdict": verdict, "reason": reason[:400],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
