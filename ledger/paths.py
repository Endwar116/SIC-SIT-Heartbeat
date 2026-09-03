"""Resolve where this installation keeps its state.

Everything lives under HEARTBEAT_HOME (default: ~/.sic-sit-heartbeat).
Nothing is hard-coded to a machine, a volume, or a person.

    HEARTBEAT_HOME/
      ledger/rounds.jsonl        append-only hash chain (never rewritten)
      ledger/STATE_CURRENT.json  latest round, atomically replaced
      ledger/events.log          human-readable one-line-per-round digest
      trash/                     soft-deleted items + TOMBSTONE.md (see rollback/)
      laws/                      incident -> law records (see laws/)
      state/                     watcher registry, pending items, misc
      logs/                      *internal-disk* logs for scheduled services
"""
import os
from pathlib import Path

HOME = Path(os.environ.get("HEARTBEAT_HOME", Path.home() / ".sic-sit-heartbeat")).expanduser()
LEDGER_DIR = HOME / "ledger"
ROUNDS = LEDGER_DIR / "rounds.jsonl"
STATE_CURRENT = LEDGER_DIR / "STATE_CURRENT.json"
EVENTS_LOG = LEDGER_DIR / "events.log"
TRASH = HOME / "trash"
LAWS = HOME / "laws"
STATE = HOME / "state"
LOGS = HOME / "logs"
WATCHER_REGISTRY = STATE / "watchers.jsonl"
PENDING = STATE / "pending.jsonl"
PREREG_EXEMPTIONS = STATE / "prereg_exemptions.jsonl"

AGENT_NAME = os.environ.get("HEARTBEAT_AGENT", "agent")
AGENT_MODEL = os.environ.get("HEARTBEAT_MODEL", "unknown")   # models cannot self-attest; set from your harness


def ensure_dirs():
    for d in (LEDGER_DIR, TRASH, LAWS, STATE, LOGS):
        d.mkdir(parents=True, exist_ok=True)
