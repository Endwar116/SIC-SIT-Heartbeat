#!/usr/bin/env bash
# run_loop.sh — keep ticking. Works as:
#   * a foreground loop        : ./heartbeat/run_loop.sh 3600
#   * a Claude Code Monitor    : Monitor(command: "./heartbeat/run_loop.sh 3600")  (each line = one event)
#   * cron                     : 0 * * * * /path/heartbeat/tick.sh   (use tick.sh directly, not this loop)
#   * launchd                  : see install/launchd/  (StartInterval, log paths on the INTERNAL disk)
# Prints exactly one line per tick, so a watcher can turn each into a notification.
INTERVAL="${1:-3600}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while true; do
  if "$HERE/tick.sh" >/tmp/.sic_tick.$$ 2>&1; then
    echo "💓 tick $(date +%H:%M) ok — $(tail -1 /tmp/.sic_tick.$$)"
  else
    echo "🔴 tick $(date +%H:%M) RED — $(tail -1 /tmp/.sic_tick.$$)"
  fi
  sleep "$INTERVAL"
done
