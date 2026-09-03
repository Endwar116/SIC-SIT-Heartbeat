#!/usr/bin/env python3
"""derive.py — build a SIC-JS 4.0 round from *truth sources*, not from memory.

The umbrella rule: every field that can drift or be derived is derived by code;
only genuinely semantic fields (context / current_action / intent) are supplied by the caller.

  field                 source                                   why not the model
  round                 last round in the ledger + 1             agents mis-increment from memory
  relation.upstream     hash of previous round (recomputed)      never trust a model-computed hash
  entity.name           HEARTBEAT_AGENT env (installation)       a global identity var goes stale
  entity.model          HEARTBEAT_MODEL env (set by harness)     a model cannot attest its own identity
  event.timestamp       system clock                             hand-written timestamps drift
  task.*                inherited from previous round            inheritance is copying, not remembering
  state.context etc.    caller                                   code cannot derive meaning, and won't pretend to

Usage (library):
    from derive import derive_state
    st = derive_state(context="...", current_action="...", pending=[...],
                      user_intent="...", system_intent="...", core_question="...",
                      description="...", trigger="...")
CLI:
    derive.py --context "..." --action "..." [--pending a,b] [--trigger "..."] | ledger.py append -
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths          # noqa: E402
from ledger import read_rounds, now_iso, TornTail   # noqa: E402


def derive_state(context, current_action, pending=None, user_intent="", system_intent="",
                 core_question="", description="", trigger="heartbeat", task=None):
    rounds = read_rounds()
    prev = rounds[-1] if rounds else None
    rnd = (prev["state"]["round"] + 1) if prev else 1
    upstream = prev["hash"][:16] if prev else None
    inherited_task = (prev["state"].get("task") if prev else None) or {
        "id": "T-1", "title": "heartbeat", "deliverable": "governed periodic tick",
        "status": "in_progress", "created_round": rnd}
    if task:
        inherited_task = {**inherited_task, **task}
    return {
        "sic_version": "4.0",
        "round": rnd,
        "entity": {"name": paths.AGENT_NAME, "model": paths.AGENT_MODEL},
        "state": {"context": context, "current_action": current_action, "pending": pending or []},
        "task": inherited_task,
        "relation": {"user": "operator", "linked_entities": [], "upstream": upstream},
        "event": {"timestamp": now_iso(), "description": description or current_action[:120],
                  "trigger": trigger},
        "intent": {"user_intent": user_intent, "system_intent": system_intent,
                   "core_question": core_question},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", required=True)
    ap.add_argument("--action", required=True)
    ap.add_argument("--pending", default="")
    ap.add_argument("--trigger", default="heartbeat")
    ap.add_argument("--user-intent", default="")
    ap.add_argument("--system-intent", default="")
    ap.add_argument("--core-question", default="")
    a = ap.parse_args()
    try:
        _ = read_rounds()
    except TornTail as e:
        print(f"❌ {e}", file=sys.stderr); sys.exit(1)
    st = derive_state(a.context, a.action,
                      pending=[p for p in a.pending.split(",") if p],
                      user_intent=a.user_intent, system_intent=a.system_intent,
                      core_question=a.core_question, trigger=a.trigger)
    print(json.dumps(st, ensure_ascii=False))


if __name__ == "__main__":
    main()
