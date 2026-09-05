#!/usr/bin/env python3
"""reminder.py — the operator's reminder (貼心叮嚀): one sentence in the operator's own words, injected at
every heartbeat.

Rules do not stop idle spin; the study measured that. What the operator can do is leave the agent a sentence —
what to do when there is nothing to do — and have the heartbeat hand that sentence back at every wake, unchanged,
as a separate line. It is the operator's voice, not the agent's, and the operator edits it without touching code:

    reminder.py set "If there is nothing to do, look at the pending list, or decide for yourself whether to take
                     a break — but there is always something: with nothing else, take a code review and go over
                     the things you are responsible for."

  reminder.py set TEXT              store the reminder ($HEARTBEAT_HOME/config/reminder.txt) with who/when/sha
  reminder.py show                  print it
  reminder.py inject                print the line the tick injects: 💬 TEXT  (+ "on break until …" if declared)
  reminder.py sha                   short fingerprint of the current text (recorded in every round)
  reminder.py break --hours H --why W    declare a break: a rest with an end and a reason is not idle spin
  reminder.py resume                end the break early
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

CONFIG = paths.HOME / "config"
TEXT = CONFIG / "reminder.txt"
META = CONFIG / "reminder.json"
BREAK = paths.STATE / "break.json"
UNSET = ("No reminder set yet. The operator leaves one in their own words — what to do when there is nothing to do: "
         "reminder.py set \"…\"")


def now():
    return datetime.now(timezone.utc).astimezone()


def text():
    try:
        t = TEXT.read_text(encoding="utf-8").strip()
        return t or None
    except OSError:
        return None


def sha():
    t = text()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:8] if t else "unset"


def active_break():
    try:
        b = json.load(open(BREAK, encoding="utf-8"))
        until = datetime.fromisoformat(b["until"])
        return b if until > now() else None
    except (OSError, ValueError, KeyError):
        return None


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set"); s.add_argument("text")
    sub.add_parser("show"); sub.add_parser("inject"); sub.add_parser("sha"); sub.add_parser("resume")
    b = sub.add_parser("break"); b.add_argument("--hours", type=float, required=True); b.add_argument("--why", required=True)
    a = ap.parse_args()
    if a.cmd == "set":
        t = a.text.strip()
        if not t:
            sys.stderr.write("❌ an empty reminder is not a reminder\n"); return 2
        CONFIG.mkdir(parents=True, exist_ok=True); TEXT.write_text(t + "\n", encoding="utf-8")
        META.write_text(json.dumps({"set_at": now().isoformat(timespec="seconds"), "by": os.environ.get("HEARTBEAT_OPERATOR", "operator"),
                                    "sha": hashlib.sha256(t.encode("utf-8")).hexdigest()[:8]}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("reminder set", META.read_text(encoding="utf-8").split('"sha": ')[1].strip(' }\n"')); return 0
    if a.cmd == "show":
        print(text() or UNSET); return 0
    if a.cmd == "sha":
        print(sha()); return 0
    if a.cmd == "break":
        if a.hours <= 0 or not a.why.strip():
            sys.stderr.write("❌ a break has an end (--hours > 0) and a reason (--why)\n"); return 2
        paths.ensure_dirs()
        until = now() + timedelta(hours=a.hours)
        BREAK.write_text(json.dumps({"until": until.isoformat(timespec="seconds"), "why": a.why.strip(),
                                     "set_at": now().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
        print("on break until", until.isoformat(timespec="minutes"), "—", a.why.strip()); return 0
    if a.cmd == "resume":
        if BREAK.exists():
            os.replace(BREAK, BREAK.with_name("break.ended.json"))
        print("resumed"); return 0
    # inject
    line = "💬 " + (text() or UNSET)
    br = active_break()
    if br:
        line += f"  (on break until {br['until'][:16]}: {br['why'][:60]})"
    print(line); return 0


if __name__ == "__main__":
    sys.exit(main())
