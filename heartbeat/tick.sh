#!/usr/bin/env bash
# tick.sh — ONE governed heartbeat.
#
# A tick is not "the agent wakes up and does stuff". A tick is a bounded, recorded unit:
#   1. checks (services / zombies / inbox / chain integrity) — machine-judged, no self-report
#   2. the agenda question: the top doable item from the pending ledger, or proof that the pile is empty
#   3. the progress question: did anything external move since the last tick? (receipts, artifacts)
#      k ticks with doable work and no progress = IDLE_SPIN: red, and the top item is locked (docs/SPEC_IDLE.md)
#   4. one SIC-JS round appended to the hash-chained ledger, carrying all of the above — composed by code
#   5. exit 1 if anything is red; and **green is silent**: no status line unless there is something to act on
#      (a red check, a next item, new inbox). The ledger round and logs/tick.log are the liveness record.
#   6. the operator's reminder (heartbeat/reminder.py) is injected as its own line at every tick.
# If nothing needs doing, the tick records "noop" and exits 0. It never invents work.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
export HEARTBEAT_HOME="${HEARTBEAT_HOME:-$HOME/.sic-sit-heartbeat}"
INBOX="${HEARTBEAT_INBOX:-$HEARTBEAT_HOME/inbox}"
PY="${PYTHON:-python3}"
mkdir -p "$HEARTBEAT_HOME" "$INBOX" "$HEARTBEAT_HOME/logs"

red=0; notes=(); detail=""
run_check () {  # name, command...
  local name="$1"; shift
  if out="$("$@" 2>&1)"; then notes+=("$name:ok"); else red=1; notes+=("$name:RED"); detail+="── $name"$'\n'"$out"$'\n'; fi
}

run_check chain    "$PY" "$ROOT/ledger/ledger.py" verify
run_check services "$PY" "$HERE/health.py"
run_check zombies  "$PY" "$HERE/zombie.py" check
inbox_n=$(find "$INBOX" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
notes+=("inbox:$inbox_n")
debts=$("$PY" "$ROOT/laws/legislate.py" debts --count 2>/dev/null || echo "?")
notes+=("laws_debts:$debts")

ext=0; [ "$inbox_n" != "0" ] && ext=1
prog="$("$PY" "$HERE/progress.py" tick --external "$ext" 2>&1)"; prc=$?
[ $prc -eq 0 ] || { red=1; detail+="── progress"$'\n'"$prog"$'\n'; }
notes+=("$prog")
rem_sha=$("$PY" "$HERE/reminder.py" sha 2>/dev/null || echo "?")
notes+=("reminder:$rem_sha")

summary="$(IFS=' '; echo "${notes[*]}")"
anchor="$("$PY" "$ROOT/ledger/derive.py" \
  --context "heartbeat tick" \
  --action "tick: $summary" \
  --trigger "scheduler" \
  --system-intent "governed periodic check; draw one item or prove the pile empty; record, do not invent work" \
| "$PY" "$ROOT/ledger/ledger.py" append - --auto-round 2>&1)" || { echo "❌ could not record the tick"; echo "$anchor"; exit 3; }

echo "$(date '+%Y-%m-%dT%H:%M:%S') rc=$red $(echo "$anchor" | tail -1) $summary" >> "$HEARTBEAT_HOME/logs/tick.log"

next_id=$(printf '%s' "$prog" | sed -n 's/.*next:\([^ ]*\).*/\1/p')
if [ $red -ne 0 ] || [ "${next_id:-none}" != "none" ] || [ "$inbox_n" != "0" ]; then
  [ -n "$detail" ] && printf '%s' "$detail"
  echo "$anchor" | tail -1
  echo "tick: $summary"
fi
# the operator's reminder is injected at every tick, as its own line — on a quiet tick it is the only line
"$PY" "$HERE/reminder.py" inject 2>/dev/null || true
exit $red
