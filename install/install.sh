#!/usr/bin/env bash
# install.sh — wire the gates into your agent harness and set up the state directory.
#
#   ./install/install.sh                # Claude Code (CLI, VS Code extension, desktop): edits ~/.claude/settings.json
#   ./install/install.sh --settings P   # a different settings.json
#   ./install/install.sh --dry-run      # show the merged JSON, change nothing
#
# What it does:  backs up settings.json  →  merges three PreToolUse hooks + one Stop hook (turn-exit)  →  creates $HEARTBEAT_HOME
# What it does not do:  touch anything else in settings.json; install schedulers (see terminal.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
SETTINGS="${HOME}/.claude/settings.json"; DRY=0; MODE=install
while [ $# -gt 0 ]; do case "$1" in
  --settings) SETTINGS="$2"; shift 2;; --dry-run) DRY=1; shift;; --uninstall) MODE=uninstall; shift;; --check) MODE=check; shift;;
  *) echo "unknown arg $1"; exit 2;; esac; done
if [ "$MODE" = check ]; then
  python3 - "$SETTINGS" "$ROOT" <<'PY2'
import json,os,sys
d=json.load(open(sys.argv[1])); bad=0
for ent in d.get("hooks",{}).get("PreToolUse",[]) + d.get("hooks",{}).get("Stop",[]):
    for h in ent.get("hooks",[]):
        cmd=h.get("command",""); tok=cmd.split()[1:2]
        if tok and tok[0].endswith(".py") and not os.path.exists(tok[0]): print("MISSING:",ent.get("matcher"),tok[0]); bad=1
print("hooks ok" if not bad else "some hook targets are missing => those gates are silently OFF"); sys.exit(bad)
PY2
  exit $?
fi
if [ "$MODE" = uninstall ]; then
  cp "$SETTINGS" "$SETTINGS.bak_$(date +%Y%m%d_%H%M%S)"
  python3 - "$SETTINGS" "$ROOT" <<'PY2'
import json,sys
d=json.load(open(sys.argv[1])); root=sys.argv[2]
pre=d.get("hooks",{}).get("PreToolUse",[])
keep=[e for e in pre if not any(root in h.get("command","") for h in e.get("hooks",[]))]
d["hooks"]["PreToolUse"]=keep
stp=d.get("hooks",{}).get("Stop",[]); keep_s=[e for e in stp if not any(root in h.get("command","") for h in e.get("hooks",[]))]
removed=(len(pre)-len(keep))+(len(stp)-len(keep_s))
if "Stop" in d.get("hooks",{}): d["hooks"]["Stop"]=keep_s
open(sys.argv[1],"w").write(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
print(f"removed {removed} hook entries pointing into {root}; ledger and trash untouched")
PY2
  exit 0
fi
export HEARTBEAT_HOME="${HEARTBEAT_HOME:-$HOME/.sic-sit-heartbeat}"
mkdir -p "$HEARTBEAT_HOME"/{ledger,trash,laws,state,logs,inbox}
[ -f "$SETTINGS" ] || { mkdir -p "$(dirname "$SETTINGS")"; echo '{}' > "$SETTINGS"; }
[ "$DRY" = 1 ] || cp "$SETTINGS" "$SETTINGS.bak_$(date +%Y%m%d_%H%M%S)"
python3 - "$SETTINGS" "$ROOT" "$DRY" <<'PY'
import json, sys
settings, root, dry = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
d = json.load(open(settings, encoding="utf-8"))
pre = d.setdefault("hooks", {}).setdefault("PreToolUse", [])
want = [
  ("Bash",     f"python3 {root}/gates/file_governance.py"),
  ("Monitor",  f"python3 {root}/gates/monitor_dedup.py"),
  ("Workflow", f"python3 {root}/gates/prereg_gate.py"),
]
have = {(h.get("matcher"), hk.get("command")) for h in pre for hk in h.get("hooks", [])}
added = []
for matcher, cmd in want:
    if (matcher, cmd) not in have:
        pre.append({"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]}); added.append(matcher)
stop = d["hooks"].setdefault("Stop", [])            # turn-exit gate: promises become items, claims carry receipts
stop_cmd = f"python3 {root}/gates/turn_exit.py"
if not any(hk.get("command") == stop_cmd for h in stop for hk in h.get("hooks", [])):
    stop.append({"matcher": "", "hooks": [{"type": "command", "command": stop_cmd}]}); added.append("Stop")
out = json.dumps(d, ensure_ascii=False, indent=2)
if dry:
    print(out)
else:
    open(settings, "w", encoding="utf-8").write(out + "\n")
print(f"hooks added: {added or 'none (already present)'}", file=sys.stderr)
PY
echo "state dir: $HEARTBEAT_HOME"
echo "next: python3 $ROOT/ledger/ledger.py verify   (empty chain is intact)"
echo "      $ROOT/heartbeat/tick.sh                 (one governed tick)"
echo "note: hooks embed this absolute path. If you move the repo, run install.sh --check (a missing target = gate silently off)."
