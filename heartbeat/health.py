#!/usr/bin/env python3
"""health.py — detect scheduled services that died *quietly*.

Incident behind this: six background services had been dead for three months. Nobody noticed,
because the failure was silent: the scheduler could not open the service's log file (it lived on
an external volume), so it gave up BEFORE running the script, returned exit 78, and wrote nothing.
Reading the log to find out why was impossible — the log was the thing it couldn't open.

So we do not look for errors in logs. We look for three shapes:
  1. exit status not in {0, -15}         (78 = EX_CONFIG: scheduler gave up before exec)
  2. declared log path that does not exist -> the job has NEVER run successfully
  3. log exists but is stale for a periodic job -> it ran once, then stopped
plus one known-bad configuration: a log path on an external/removable volume.

Discipline (docs/SPEC_INCIDENT_LAW.md, law 007): these are SYMPTOMS. Before declaring a service
dead, read the record the service writes for itself, and rule out "finished its job on purpose".
The agent that wrote this misdiagnosed a completed 12-run job as "never ran" by skipping that step.

macOS: launchd user agents.  Linux: systemd --user (best effort).  Others: nothing to inspect, exit 0.
"""
import os
import plistlib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXTERNAL_PREFIXES = tuple(os.environ.get("HEARTBEAT_EXTERNAL_PREFIXES", "/Volumes/,/mnt/,/media/").split(","))
_FILTER_ENV = os.environ.get("HEARTBEAT_SERVICE_FILTER")
LABEL_FILTER = re.compile(_FILTER_ENV) if _FILTER_ENV else None   # None => only jobs with a plist in ~/Library/LaunchAgents
OK_EXITS = {0, -15, -9}


def macos_jobs():
    la = Path.home() / "Library/LaunchAgents"
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    jobs = []
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        pid, status, label = parts[0], parts[1], parts[2].strip()
        plist = la / f"{label}.plist"
        if LABEL_FILTER is None:
            if not plist.exists():
                continue
        elif not LABEL_FILTER.search(label):
            continue
        d = None
        if plist.exists():
            try:
                d = plistlib.load(open(plist, "rb"))
            except Exception:
                d = None
        jobs.append({"label": label, "running": pid not in ("-", ""), "status": status, "conf": d,
                     "log": (d or {}).get("StandardOutPath"), "err": (d or {}).get("StandardErrorPath"),
                     "periodic": bool((d or {}).get("StartInterval") or (d or {}).get("StartCalendarInterval"))})
    return jobs


def linux_jobs():
    try:
        out = subprocess.run(["systemctl", "--user", "list-units", "--type=service,timer", "--all", "--no-legend", "--plain"],
                             capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    jobs = []
    for line in out.splitlines():
        cols = line.split()
        if len(cols) < 4 or (LABEL_FILTER and not LABEL_FILTER.search(cols[0])):
            continue
        if cols[2] not in ("failed", "active"):
            continue                                  # inactive/dead timers are not failures
        jobs.append({"label": cols[0], "running": cols[3] == "running", "status": "0" if cols[2] == "active" else "1",
                     "conf": None, "log": None, "err": None, "periodic": cols[0].endswith(".timer")})
    return jobs


def hook_targets_missing():
    """A hook whose command file is gone exits 127, which the harness treats as non-blocking: the gate is silently off."""
    import json
    missing = []
    for sp in (Path.home() / ".claude/settings.json",):
        if not sp.exists():
            continue
        try:
            d = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for ent in (d.get("hooks", {}) or {}).get("PreToolUse", []) or []:
            for h in ent.get("hooks", []) or []:
                cmd = h.get("command", "")
                parts = cmd.split()
                for tok in parts[1:2]:
                    if tok.endswith(".py") and not os.path.exists(os.path.expanduser(tok)):
                        missing.append(f"{ent.get('matcher')}: {tok}")
    return missing


def main():
    stale_h = float(os.environ.get("HEARTBEAT_STALE_HOURS", "24"))
    jobs = macos_jobs() if sys.platform == "darwin" else (linux_jobs() if sys.platform.startswith("linux") else [])
    now = datetime.now()
    problems = []
    for j in jobs:
        issues = []
        try:
            st = int(j["status"])
        except (TypeError, ValueError):
            st = None
        if st is not None and st not in OK_EXITS:
            issues.append(f"exit status {st}" + (" = EX_CONFIG: the scheduler gave up before running it "
                                                 "(most often: it cannot open the declared log path)" if st == 78 else ""))
        for k in ("log", "err"):
            v = j.get(k)
            if v and v.startswith(EXTERNAL_PREFIXES):
                issues.append(f"{k} path on an external volume ({v}) — known to break scheduling; move it under ~/")
        if j.get("log"):
            if not os.path.exists(j["log"]):
                issues.append(f"declared log does not exist ({j['log']}) => this job has never run successfully")
            elif j["periodic"]:
                age_h = (now - datetime.fromtimestamp(os.path.getmtime(j["log"]))).total_seconds() / 3600
                if age_h > stale_h:
                    issues.append(f"log stale for {age_h/24:.0f} days => ran once, then stopped")
        if issues:
            problems.append((j["label"], j["running"], issues))
    for m in hook_targets_missing():
        problems.append((f"hook {m}", False, ["gate command file missing => the gate is silently OFF (exit 127 is non-blocking)"]))
    print(f"checked {len(jobs)} services, {len(problems)} with problems")
    for label, running, issues in problems:
        print(f"⚠️ {label}{' (process running)' if running else ''}")
        for i in issues:
            print(f"     {i}")
    if problems:
        print("\nBefore acting: read each service's OWN record (its run log / state file). "
              "Rule out 'completed on purpose' before declaring it dead.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
