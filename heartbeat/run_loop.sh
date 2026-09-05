#!/usr/bin/env bash
# run_loop.sh — keep ticking. Two modes:
#   run_loop.sh [INTERVAL]            timer: one tick every INTERVAL seconds (default 3600)
#   run_loop.sh --event [FALLBACK]    event-gated: tick when something happens (inbox, pending ledger, `touch
#                                     $HEARTBEAT_HOME/wake`), else only every FALLBACK seconds (default 21600)
#                                     as a liveness proof. This is the mode that removes timer-driven idle spin.
# Registers itself in the watcher registry (so a duplicate loop is caught) and unregisters on exit.
set -u
MODE="timer"; INTERVAL="${1:-3600}"
if [ "${1:-}" = "--event" ]; then MODE="event"; INTERVAL="${2:-${HEARTBEAT_FALLBACK:-21600}}"; fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
export HEARTBEAT_HOME="${HEARTBEAT_HOME:-$HOME/.sic-sit-heartbeat}"; mkdir -p "$HEARTBEAT_HOME/logs"
ID="loop-$$-$(date +%s)"
python3 "$ROOT/gates/monitor_dedup.py" register "$ID" "run_loop.sh $MODE $INTERVAL" --desc "heartbeat loop ($MODE, ${INTERVAL}s)" >/dev/null 2>&1 || true
TMP="$(mktemp "$HEARTBEAT_HOME/logs/.tick.XXXXXX")"
cleanup() { python3 "$ROOT/gates/monitor_dedup.py" stop "$ID" >/dev/null 2>&1 || true; [ -f "$TMP" ] && mv "$TMP" "$HEARTBEAT_HOME/logs/last_tick.log" 2>/dev/null; }
trap cleanup EXIT INT TERM
while true; do
  reason="timer"
  if [ "$MODE" = "event" ]; then reason="$(python3 "$HERE/wake.py" wait --fallback "$INTERVAL")"; fi
  if "$HERE/tick.sh" >"$TMP" 2>&1; then
    last="$(tail -1 "$TMP")"; [ -n "$last" ] && echo "💓 tick $(date +%H:%M) ok ($reason) — $last"   # a silent green tick prints nothing here either
  else echo "🔴 tick $(date +%H:%M) RED ($reason) — $(tail -1 "$TMP")"; fi
  [ "$MODE" = "event" ] || sleep "$INTERVAL"
done
