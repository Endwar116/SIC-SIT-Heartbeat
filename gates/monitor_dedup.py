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
from _hook import read_payload, block, allow, guarded  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

GATE = "monitor-dedup"
WATCHER_TOOLS = {"Monitor", "StartWatcher", "Watch"}


def fingerprint(cmd: str):
    """Loop shape, not literal text: (is a while-true loop, sleep seconds, topic keyword).
    Registries are written by humans and often hold a summary, not the exact command. Two
    heartbeats that differ only in echo text must still collide."""
    c = (cmd or "").lower()
    loop = bool(re.search(r"while\s+true|while\s+:|for\s*\(\(\s*;;", c))
    m = re.search(r"sleep\s+(\d+)", c)
    topic = "heartbeat" if re.search(r"\b(?:heartbeat|tick)\b|心跳", c) else ("tail" if re.search(r"\btail\s+-[fF]\b", c) else "")
    return (loop, m.group(1) if m else None, topic)


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


def register(task_id, cmd, desc="", status="active"):
    paths.ensure_dirs()
    with open(paths.WATCHER_REGISTRY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": __import__("datetime").datetime.now().astimezone().isoformat(timespec="minutes"),
                            "task_id": task_id, "cmd": cmd, "desc": desc, "status": status}, ensure_ascii=False) + "\n")


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("register", "stop"):
        # CLI use: monitor_dedup.py register <task_id> "<exact command>" [--desc "..."]  |  stop <task_id>
        if argv[0] == "register" and len(argv) >= 3:
            desc = argv[argv.index("--desc") + 1] if "--desc" in argv else ""
            register(argv[1], argv[2], desc); print(f"registered {argv[1]}"); sys.exit(0)
        if argv[0] == "stop" and len(argv) >= 2:
            register(argv[1], "", "", "stopped"); print(f"stopped {argv[1]}"); sys.exit(0)
        print(__doc__); sys.exit(2)
    p, problem = read_payload()
    if problem:
        allow(GATE, f"unparseable payload allowed: {problem}")
    if p.get("tool_name") not in WATCHER_TOOLS:
        allow()
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    if not cmd:
        allow()
    n = norm(cmd)
    fp = fingerprint(cmd)
    for r in active_entries():
        rn = norm(r.get("cmd", ""))
        same_shape = fp[0] and fp[2] and fingerprint(r.get("cmd", "")) == fp
        same_tokens = rn and set(rn.split()) == set(n.split())
        if rn == n or same_tokens or same_shape:
            block(
                f"an equivalent watcher is already registered as active.\n"
                f"   existing: task_id={r.get('task_id')} desc={r.get('desc')} since {r.get('ts')}\n"
                f"   Verify it is really dead (wait for its next tick, or stop it) before mounting again.\n"
                f"   If both must coexist, mark the old entry stopped in {paths.WATCHER_REGISTRY} first.",
                GATE)
    allow()


if __name__ == "__main__":
    guarded(GATE, main)
