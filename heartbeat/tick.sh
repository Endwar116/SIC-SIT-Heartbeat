#!/usr/bin/env bash
# tick.sh — ONE governed heartbeat.
#
# A tick is not "the agent wakes up and does stuff". A tick is a bounded, recorded unit:
#   1. checks (services / zombies / inbox / chain integrity) — machine-judged, no self-report
#   2. one SIC-JS round appended to the hash-chained ledger, carrying the check results
#   3. a non-zero exit if anything is red, so the scheduler/operator can see it
# If nothing needs doing, the tick records "nothing to do" and exits 0. It never invents work.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
export HEARTBEAT_HOME="${HEARTBEAT_HOME:-$HOME/.sic-sit-heartbeat}"
INBOX="${HEARTBEAT_INBOX:-$HEARTBEAT_HOME/inbox}"
PY="${PYTHON:-python3}"
mkdir -p "$HEARTBEAT_HOME" "$INBOX"

red=0; notes=()
run_check () {  # name, command...
  local name="$1"; shift
  if out="$("$@" 2>&1)"; then notes+=("$name:ok"); else red=1; notes+=("$name:RED"); printf '── %s\n%s\n' "$name" "$out"; fi
}

run_check chain    "$PY" "$ROOT/ledger/ledger.py" verify
run_check services "$PY" "$HERE/health.py"
run_check zombies  "$PY" "$HERE/zombie.py" check
inbox_n=$(find "$INBOX" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
notes+=("inbox:$inbox_n")
debts=$("$PY" "$ROOT/laws/legislate.py" debts --count 2>/dev/null || echo "?")
notes+=("laws_debts:$debts")

summary="$(IFS=' '; echo "${notes[*]}")"
"$PY" "$ROOT/ledger/derive.py" \
  --context "heartbeat tick" \
  --action "tick: $summary" \
  --trigger "scheduler" \
  --system-intent "governed periodic check; record, do not invent work" \
| "$PY" "$ROOT/ledger/ledger.py" append - --auto-round || { echo "❌ could not record the tick"; exit 3; }

echo "tick: $summary"
exit $red
