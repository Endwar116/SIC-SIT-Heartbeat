#!/usr/bin/env bash
# install.sh — wire the gates into your agent harness and set up the state directory.
#
#   ./install/install.sh                # Claude Code (CLI, VS Code extension, desktop): edits ~/.claude/settings.json
#   ./install/install.sh --settings P   # a different settings.json
#   ./install/install.sh --dry-run      # show the merged JSON, change nothing
#
# What it does:  backs up settings.json  →  merges three PreToolUse hooks  →  creates $HEARTBEAT_HOME
# What it does not do:  touch anything else in settings.json; install schedulers (see terminal.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
SETTINGS="${HOME}/.claude/settings.json"; DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --settings) SETTINGS="$2"; shift 2;; --dry-run) DRY=1; shift;; *) echo "unknown arg $1"; exit 2;; esac; done
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
