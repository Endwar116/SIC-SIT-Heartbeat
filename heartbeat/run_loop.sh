#!/usr/bin/env bash
# run_loop.sh — keep ticking. Works as a foreground loop, a Claude Code Monitor command, or under launchd.
# Registers itself in the watcher registry on start and marks itself stopped on exit, so
# gates/monitor_dedup.py can refuse a second identical loop.
INTERVAL="${1:-3600}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"
export HEARTBEAT_HOME="${HEARTBEAT_HOME:-$HOME/.sic-sit-heartbeat}"; mkdir -p "$HEARTBEAT_HOME/logs"
ID="loop-$$-$(date +%s)"
python3 "$ROOT/gates/monitor_dedup.py" register "$ID" "run_loop.sh $INTERVAL" --desc "heartbeat loop every ${INTERVAL}s" >/dev/null 2>&1 || true
TMP="$(mktemp "$HEARTBEAT_HOME/logs/.tick.XXXXXX")"
cleanup() { python3 "$ROOT/gates/monitor_dedup.py" stop "$ID" >/dev/null 2>&1 || true; [ -f "$TMP" ] && mv "$TMP" "$HEARTBEAT_HOME/logs/last_tick.log" 2>/dev/null; }
trap cleanup EXIT INT TERM
while true; do
  if "$HERE/tick.sh" >"$TMP" 2>&1; then echo "💓 tick $(date +%H:%M) ok — $(tail -1 "$TMP")"
  else echo "🔴 tick $(date +%H:%M) RED — $(tail -1 "$TMP")"; fi
  sleep "$INTERVAL"
done
