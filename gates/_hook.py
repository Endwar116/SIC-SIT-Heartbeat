"""Shared plumbing for PreToolUse-style gates.

Contract (Claude Code hooks; other harnesses can adapt):
  * stdin  : JSON {"tool_name": str, "tool_input": {...}}
  * exit 0 : allow          * exit 2 : BLOCK (stderr is shown to the agent)
  * exit 1 : warn only — the action still runs. Never use it for policy.
Gates must be fast (<500 ms) and must never crash-block on their own bugs: a gate that raises
ALLOWS, and records the anomaly. Every verdict — allow, block, warn, error — is appended to
state/gate_decisions.jsonl so the audit trail is complete, not just the blocks.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

ALLOW, BLOCK = 0, 2


def read_payload():
    """Return (payload, problem). payload is a dict with str tool_name and dict tool_input, or None."""
    try:
        p = json.load(sys.stdin)
    except Exception as e:  # noqa: BLE001
        return None, f"unparseable stdin: {e.__class__.__name__}"
    if not isinstance(p, dict) or not isinstance(p.get("tool_name"), str):
        return None, "payload is not {tool_name: str, ...}"
    ti = p.get("tool_input")
    if ti is None:
        p["tool_input"] = {}
    elif not isinstance(ti, dict):
        return None, "tool_input is not an object"
    return p, None


def record(gate, verdict, reason=""):
    try:
        paths.ensure_dirs()
        with open(paths.STATE / "gate_decisions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "gate": gate, "verdict": verdict, "reason": str(reason)[:400],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def block(reason, gate):
    sys.stderr.write(f"⛔ {gate}: {reason}\n")
    record(gate, "blocked", reason)
    sys.exit(BLOCK)


def warn(reason, gate):
    """Allow, but say so. For high-false-positive patterns (tee, sed -i, pipes into a shell)."""
    sys.stderr.write(f"⚠️  {gate}: {reason}\n")
    record(gate, "warned", reason)
    sys.exit(ALLOW)


def allow(gate=None, note="allowed"):
    if gate:
        record(gate, "allowed", note)
    sys.exit(ALLOW)


def guarded(gate, fn):
    """Run a gate's main. Any exception => allow + record 'error'. Gates must not become the outage."""
    try:
        fn()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        record(gate, "error", f"{e.__class__.__name__}: {e}")
        sys.stderr.write(f"⚠️  {gate}: gate error ({e.__class__.__name__}); allowing.\n")
        sys.exit(ALLOW)
