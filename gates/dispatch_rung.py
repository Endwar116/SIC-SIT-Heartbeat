#!/usr/bin/env python3
"""dispatch_rung.py — declare which rung of the dispatch ladder you are using (PreToolUse: Agent / Workflow).

law-009: when an agent needs workers it walks an ordered ladder and PROBES each rung instead of assuming:
    1 worker pool  →  2 free/cheap cloud API  →  3 local model  →  4 cheaper cloud model  →  5 flagship inline (LAST, disclosed)
The incident: the worker pool died on provider overload and the agent silently fell back to rung 5 without
probing 2–4 and without telling the operator. Cost is the operator's resource, not the agent's.

This gate cannot judge whether the rung is *right*; it can make the choice *explicit and logged*. A dispatch
prompt must carry a tag:
    RUNG: <1-5|worker|free|local|cheap|flagship> — <one line why the higher rungs were not used>
Default is WARN (allow + stderr + record). Set HEARTBEAT_RUNG_STRICT=1 to block instead.
OPT-IN: not installed by install.sh. Add a PreToolUse entry with matcher "Agent|Workflow" if you want it —
it will fire on every subagent call in that harness, including a human's own.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook import read_payload, block, warn, allow, guarded  # noqa: E402

GATE = "dispatch-rung"
TAG = re.compile(r"\bRUNG:\s*(?:[1-5]|worker|free|local|cheap|flagship)\b[^\n]{0,200}", re.I)


def main():
    p, problem = read_payload()
    if problem:
        allow(GATE, f"unparseable payload allowed: {problem}")
    if p["tool_name"] not in ("Agent", "Workflow"):
        allow()
    ti = p["tool_input"]
    text = " ".join(str(ti.get(k, "")) for k in ("prompt", "script", "description"))
    m = TAG.search(text)
    if m:
        allow(GATE, f"rung declared: {m.group(0)[:120]}")
    msg = ("no RUNG declared for this dispatch. Add to the prompt:  RUNG: <worker|free|local|cheap|flagship> — <why higher rungs were skipped>\n"
           "   Ladder (law-009): worker pool → free/cheap API → local model → cheaper cloud model → flagship inline (last, disclosed).")
    if os.environ.get("HEARTBEAT_RUNG_STRICT") == "1":
        block(msg, GATE)
    warn(msg, GATE)


if __name__ == "__main__":
    guarded(GATE, main)
