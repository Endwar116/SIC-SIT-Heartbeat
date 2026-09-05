#!/usr/bin/env python3
"""turn_exit.py — the forced dual exit at the turn boundary (Claude Code `Stop` hook).

An agent turn can end on three things that leave no trace in any ledger: a promise ("I'll do X later"),
a bare completion claim ("done"), or silence while a locked item waits. Each of those is the entrance to
idle spin, and each is invisible to the next turn or the next model instance. This hook closes the exits:

  1. locked item     state/locked_item.json (set by progress.py on IDLE_SPIN) — the turn may end only after
                     the item was closed with a receipt or blocked on a concrete, named blocker.   → block
  2. promise         a promise marker in the last reply with no pending item opened this turn, and no
                     "[pending:<id>]" reference to an open item.                                      → block once
  3. completion      a completion marker with no checkable receipt token in the same reply.          → warn

Payload: {"transcript_path": ..., "stop_hook_active": bool, ...}. When the harness re-runs the turn because of a
stop hook, stop_hook_active is true and this gate never blocks again (no loops). A blocked message is also
remembered by hash so the same text is never blocked twice. Markers are configurable in
$HEARTBEAT_HOME/config/turn_exit.json ({"promise": [...], "completion": [...]}); defaults cover English and Chinese.
Exit codes: 0 allow, 2 block (reason on stderr, shown to the agent). Every verdict lands in state/gate_decisions.jsonl.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook import block, warn, allow, guarded, record  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "heartbeat"))
import paths  # noqa: E402
import zombie  # noqa: E402

GATE = "turn-exit"
DEFAULT_PROMISE = ["i will ", "i'll ", "i’ll ", "will do", "later i", "going to ", "todo:", "next i",
                   "我會", "我來", "等下", "稍後", "接下來我", "下次", "排進", "之後我", "會補", "再來"]
DEFAULT_COMPLETION = ["done", "completed", "finished", "fixed", "pushed", "shipped",
                      "已完成", "做完了", "修好了", "已推", "已修", "已送", "已落盤", "已登錄", "完成了"]
SEEN = paths.STATE / "turn_exit_seen.json"


def markers():
    p = paths.HOME / "config" / "turn_exit.json"
    try:
        d = json.load(open(p, encoding="utf-8"))
        return [m.lower() for m in d.get("promise", DEFAULT_PROMISE)], [m.lower() for m in d.get("completion", DEFAULT_COMPLETION)]
    except Exception:  # noqa: BLE001
        return DEFAULT_PROMISE, DEFAULT_COMPLETION


def parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def last_turn(transcript_path):
    """(last user timestamp, last assistant text) from a JSONL transcript; ('', '') if unreadable."""
    user_ts, text = "", ""
    try:
        for line in open(transcript_path, encoding="utf-8"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message") or {}
            c = m.get("content")
            if d.get("type") == "user" or m.get("role") == "user":
                if isinstance(c, str) or (isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in c)):
                    user_ts = d.get("timestamp", user_ts); text = ""
            elif d.get("type") == "assistant" or m.get("role") == "assistant":
                if isinstance(c, list):
                    t = "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                else:
                    t = c if isinstance(c, str) else ""
                if t.strip():
                    text = t
    except OSError:
        return "", ""
    return user_ts, text


def seen(text):
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        d = json.load(open(SEEN, encoding="utf-8")) if SEEN.exists() else {}
    except ValueError:
        d = {}
    hit = h in d
    d[h] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    paths.ensure_dirs(); SEEN.write_text(json.dumps(dict(list(d.items())[-200:])), encoding="utf-8")
    return hit


def main():
    try:
        p = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        allow(GATE, "unparseable payload")
    if not isinstance(p, dict):
        allow(GATE, "payload is not an object")
    if p.get("stop_hook_active"):
        allow(GATE, "stop_hook_active: harness re-entry, never block twice")
    user_ts, text = last_turn(p.get("transcript_path", ""))
    low = text.lower()
    items = zombie.load()

    # 1. locked item — forced dual exit
    lock = paths.STATE / "locked_item.json"
    if lock.exists():
        try:
            L = json.load(open(lock, encoding="utf-8"))
        except ValueError:
            L = {}
        it = items.get(L.get("id"), {})
        released = bool(it.get("closed")) or (it.get("blocked_at", "") >= L.get("locked_at", "") and bool(it.get("blocker")))
        if released:
            os.replace(lock, lock.with_name("locked_item.released.json"))
        elif not seen("lock:" + L.get("id", "") + text):
            block(f"locked item {L.get('id')} ('{L.get('title', '')[:60]}') has had no progress for {L.get('streak')} ticks. "
                  f"End this turn with a receipt (heartbeat/zombie.py close {L.get('id')} --receipt \"<path/hash/exit code>\") "
                  f"or a named blocker (heartbeat/zombie.py block {L.get('id')} --on \"<who/what/when>\"). Silence is not an exit.", GATE)

    # 2. promise without an item
    prom, comp = markers()
    hit = next((m for m in prom if m in low), None)
    if hit:
        ok = False
        for ref in re.findall(r"\[pending:([\w.-]+)\]", text):
            if ref in items and not items[ref].get("closed"):
                ok = True
        t0 = parse_ts(user_ts)
        if not ok and t0 is not None:
            for it in items.values():
                t1 = parse_ts(it.get("opened_at"))
                if t1 and t1 >= t0 and not it.get("closed"):
                    ok = True
        if not ok and t0 is None:
            ok = True  # cannot tell when the turn started: do not block on a guess
        if not ok and not seen("promise:" + text):
            block(f"promise detected ('{hit.strip()}…') but no pending item was opened this turn. Record it — "
                  f"heartbeat/zombie.py open <id> \"<what>\" [--pile operator|others --pre \"<what can be prepared now>\"] "
                  f"and cite it as [pending:<id>] — or drop the promise. A promise that is not an item vanishes.", GATE)

    # 3. completion claim without a receipt
    if any(m in low for m in comp):
        ok, why = zombie.receipt_checkable(text)
        if not ok:
            warn("completion claimed with no checkable receipt in the same reply (a path that exists, a hash, an exit code, "
                 "a test count). Recorded as a claim, not as done.", GATE)
    allow(GATE, "clean exit")


if __name__ == "__main__":
    guarded(GATE, main)
