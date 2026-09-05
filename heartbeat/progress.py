#!/usr/bin/env python3
"""progress.py — the progress token and the livelock detector.

A scheduled agent that wakes, reads everything, and reports "nothing to do" is not idle — it is in a livelock:
alive, busy, no progress. Classical progress monitoring assumes the monitored thread does not lie about
progress; an agent can. So the token is not the agent's word but an external state change:
  * a pending item closed with a checkable receipt (heartbeat/zombie.py close), or
  * a change under $HEARTBEAT_HOME/artifacts/ (drop work products there).

  progress.py tick [--external 0|1]     classify this tick and update state/progress.json; exit 1 on IDLE_SPIN
      exit:progress(n)    n receipts landed since the last tick             streak reset
      exit:noop(...)      the doable pile is empty (its snapshot hash is recorded), nothing to invent —
                          or a break was declared (reminder.py break): a rest with an end and a reason is not spin
      exit:spin(k)        doable work exists and nothing external moved, k < K            (warning)
      exit:IDLE_SPIN(k)   k ≥ K (HEARTBEAT_IDLE_K, default 3): red; the top item is locked for the next turn
  progress.py report                    ticks, empty wake-ups and their ratio — the study's 47–53 % baseline metric

Over-production is the mirror fault: more than HEARTBEAT_MAX_DISPATCH (default 8) subagent dispatches in one
tick (counted from gate_decisions.jsonl) tags the round `over-production`.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
import zombie  # noqa: E402
import reminder  # noqa: E402

STATE_FILE = paths.STATE / "progress.json"
LOCK = paths.STATE / "locked_item.json"
ARTIFACTS = paths.HOME / "artifacts"
GATE_LOG = paths.STATE / "gate_decisions.jsonl"


def artifacts_fp():
    h = hashlib.sha256()
    if ARTIFACTS.exists():
        for p in sorted(ARTIFACTS.rglob("*")):
            if p.is_file():
                st = p.stat(); h.update(f"{p.relative_to(ARTIFACTS)}:{st.st_size}:{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def gate_lines():
    return [l for l in open(GATE_LOG, encoding="utf-8")] if GATE_LOG.exists() else []


def load_state():
    if STATE_FILE.exists():
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"streak": 0, "ticks": 0, "empty": 0, "spins": 0, "receipts": 0, "artifacts": None, "gd_lines": 0, "last_tick_at": None}


def save_state(st):
    paths.ensure_dirs()
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, STATE_FILE)


def cmd_tick(external):
    K = int(os.environ.get("HEARTBEAT_IDLE_K", "3")); maxd = int(os.environ.get("HEARTBEAT_MAX_DISPATCH", "8"))
    st = load_state(); items = zombie.load()
    receipts = sum(1 for i in items.values() if i.get("closed")) + sum(len(i.get("notes", [])) for i in items.values())
    doable = zombie.doable(items) or zombie.evergreen(items)     # evergreen = the operator's "there is always something"
    snap = zombie.snapshot(items); afp = artifacts_fp(); br = reminder.active_break()
    inbox = paths.HOME / "inbox"; inbox_n = sum(1 for p in inbox.iterdir() if p.is_file()) if inbox.exists() else 0
    gl = gate_lines(); new_gl = gl[st["gd_lines"]:]
    dispatch = sum(1 for l in new_gl if '"gate": "dispatch-rung"' in l)
    new_receipts = receipts - st["receipts"]
    progress = new_receipts > 0 or (st["artifacts"] is not None and afp != st["artifacts"])
    st["ticks"] += 1; rc = 0
    if progress:
        exit_ = f"progress({new_receipts})"; st["streak"] = 0
        if LOCK.exists():
            os.replace(LOCK, LOCK.with_name("locked_item.released.json"))
    elif br:
        exit_ = f"noop(break until {br['until'][:16]})"; st["breaks"] = st.get("breaks", 0) + 1   # a declared rest is not spin
    elif not doable:
        exit_ = f"noop(queue_empty sha={snap['sha256'][:12]})"; st["streak"] = 0; st["empty"] += 1
    else:
        st["streak"] += 1; st["empty"] += 1
        if st["streak"] >= K:
            exit_ = f"IDLE_SPIN({st['streak']})"; st["spins"] += 1; rc = 1
            paths.ensure_dirs()
            LOCK.write_text(json.dumps({"id": doable[0]["id"], "title": doable[0].get("title", ""), "locked_at": zombie.now_iso(),
                                        "streak": st["streak"]}, ensure_ascii=False), encoding="utf-8")
        else:
            exit_ = f"spin({st['streak']})"
    over = f" over-production(dispatch={dispatch}>{maxd})" if dispatch > maxd else ""
    st.update(receipts=receipts, artifacts=afp, gd_lines=len(gl), last_tick_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    save_state(st)
    nxt = doable[0]["id"] if doable else "none"
    print(f"exit:{exit_} next:{nxt} doable:{len(doable)} inbox:{inbox_n} dispatch:{dispatch}{over}")
    return rc


def cmd_report():
    st = load_state()
    print(json.dumps({"ticks": st["ticks"], "empty": st["empty"], "empty_ratio": round(st["empty"] / st["ticks"], 3) if st["ticks"] else 0.0,
                      "spins": st["spins"], "streak": st["streak"], "locked": LOCK.exists()}))
    return 0


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick"); t.add_argument("--external", default="0")
    sub.add_parser("report")
    a = ap.parse_args()
    return cmd_tick(a.external == "1") if a.cmd == "tick" else cmd_report()


if __name__ == "__main__":
    sys.exit(main())
