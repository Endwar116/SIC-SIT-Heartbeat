#!/usr/bin/env python3
"""monitor_dedup.py — no duplicate watchers (PreToolUse: Monitor / any 'start watcher' tool).

Incident behind this gate: after a model switch the agent *assumed* its clocks had died
(that had happened once before) and remounted them. The old clocks were alive. Result: three
heartbeats firing. Pattern-matching a past failure replaced checking the registry.

Rule: before mounting a watcher, read the registry. An equivalent active entry => block,
and tell the agent to verify the old one is dead (wait for its tick, or stop it) first.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook import read_payload, block, allow  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

GATE = "monitor-dedup"
WATCHER_TOOLS = {"Monitor", "StartWatcher", "Watch"}


def norm(cmd: str) -> str:
    c = re.sub(r"\s+", " ", (cmd or "").strip())
    c = re.sub(r"\$\(date[^)]*\)", "DATE", c)
    c = re.sub(r"[\"']", "", c)
    c = re.sub(r"-n\s*\d+", "-n N", c)
    return c.lower()


def active_entries():
    if not paths.WATCHER_REGISTRY.exists():
        return []
    latest = {}
    for line in open(paths.WATCHER_REGISTRY, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("task_id"):
            latest[r["task_id"]] = r          # later lines override (stopped overrides active)
    return [r for r in latest.values() if r.get("status") == "active"]


def main():
    p = read_payload()
    if not p or p.get("tool_name") not in WATCHER_TOOLS:
        allow()
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    if not cmd:
        allow()
    n = norm(cmd)
    for r in active_entries():
        rn = norm(r.get("cmd", ""))
        if rn == n or (len(n) > 20 and rn and rn in n):
            block(
                f"an equivalent watcher is already registered as active.\n"
                f"   existing: task_id={r.get('task_id')} desc={r.get('desc')} since {r.get('ts')}\n"
                f"   Verify it is really dead (wait for its next tick, or stop it) before mounting again.\n"
                f"   If both must coexist, mark the old entry stopped in {paths.WATCHER_REGISTRY} first.",
                GATE)
    allow()


if __name__ == "__main__":
    main()
