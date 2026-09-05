#!/usr/bin/env python3
"""wake.py — event-gated wake with a liveness fallback.

A timer wakes the agent whether or not anything happened, and a woken turn must produce something — that is the
root of idle spin. So the loop waits for an *event* and only falls back to a timer for liveness:
  event:wake      $HEARTBEAT_HOME/wake was touched (an operator or another process asked for a tick)
  event:inbox     a file appeared in or left $HEARTBEAT_HOME/inbox
  event:pending   state/pending.jsonl changed (someone opened, closed or blocked an item)
  fallback        nothing happened for --fallback seconds (HEARTBEAT_FALLBACK, default 21600): tick anyway,
                  so a silent installation still proves it is alive at least every fallback interval

  wake.py wait [--fallback SECONDS] [--poll SECONDS]      blocks, prints the reason, exit 0
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402


def wait(fallback, poll):
    inbox = paths.HOME / "inbox"; wakef = paths.HOME / "wake"; pend = paths.PENDING
    inbox_sig = lambda: sorted(p.name for p in inbox.iterdir()) if inbox.exists() else []  # noqa: E731
    pend_sig = lambda: pend.stat().st_mtime_ns if pend.exists() else 0  # noqa: E731
    i0, p0, start = inbox_sig(), pend_sig(), time.time()
    while True:
        if wakef.exists():
            paths.ensure_dirs(); os.replace(wakef, paths.STATE / "last_wake"); print("event:wake"); return 0
        if inbox_sig() != i0:
            print("event:inbox"); return 0
        if pend_sig() != p0:
            print("event:pending"); return 0
        if time.time() - start >= fallback:
            print("fallback"); return 0
        time.sleep(poll)


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wait"); w.add_argument("--fallback", type=float, default=float(os.environ.get("HEARTBEAT_FALLBACK", "21600")))
    w.add_argument("--poll", type=float, default=0.5)
    a = ap.parse_args()
    return wait(a.fallback, a.poll)


if __name__ == "__main__":
    sys.exit(main())
