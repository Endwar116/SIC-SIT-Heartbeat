#!/usr/bin/env python3
"""ledger.py — append-only, hash-chained ledger of SIC-JS 4.0 rounds.

Design (see docs/SPEC_LEDGER.md):
  * One round = one JSON line ("wrapper") in rounds.jsonl:
        {"seq", "logged_at", "hash", "prev_hash", "state": <SIC-JS 4.0 block>}
  * hash = sha256(prev_hash + canonical(state)); canonical = sorted keys, compact separators.
    Editing any past round breaks every hash after it.
  * The file is append-only. Nothing here ever rewrites a line.
  * STATE_CURRENT.json is replaced atomically (tempfile + fsync + os.replace).
  * Governance: the agent may not mark its own task completed/dismissed/archived.
    We do not block it (the ledger records, gates enforce) but we flag it loudly.

CLI:
  ledger.py append -            read a SIC-JS state JSON from stdin, append a round
  ledger.py verify              walk the chain, recompute every hash, report first break
  ledger.py tail [n]            show last n rounds (default 5)
  ledger.py current             print STATE_CURRENT.json
Exit: 0 ok | 1 verification failed | 2 usage / validation error
"""
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

SELF_CLOSE_STATES = {"completed", "dismissed", "archived"}
REQUIRED_TOP = ("sic_version", "round", "entity", "state", "relation", "event", "intent")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def chain_hash(prev_hash: str, state: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(state)).encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_rounds():
    if not paths.ROUNDS.exists():
        return []
    out = []
    with open(paths.ROUNDS, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"ledger corrupt at line {n}: {e}")
    return out


def validate_state(state: dict):
    missing = [k for k in REQUIRED_TOP if k not in state]
    if missing:
        raise ValueError(f"SIC-JS block missing required top-level keys: {missing}")
    if not isinstance(state.get("round"), int):
        raise ValueError("round must be an integer")
    st = state.get("task", {}).get("status")
    flag = None
    if st in SELF_CLOSE_STATES:
        flag = "AI_SELF_CLOSED"
    return flag


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append(state: dict) -> dict:
    paths.ensure_dirs()
    flag = validate_state(state)
    rounds = read_rounds()
    prev_hash = rounds[-1]["hash"] if rounds else "0" * 64
    seq = (rounds[-1]["seq"] + 1) if rounds else 1
    wrapper = {
        "seq": seq,
        "logged_at": now_iso(),
        "hash": chain_hash(prev_hash, state),
        "prev_hash": prev_hash,
        "state": state,
    }
    if flag:
        wrapper["governance_flag"] = flag
    line = json.dumps(wrapper, ensure_ascii=False) + "\n"
    # POSIX append of one line; fsync so a crash cannot leave a torn tail.
    with open(paths.ROUNDS, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    atomic_write(paths.STATE_CURRENT, json.dumps(state, ensure_ascii=False, indent=1))
    digest = state.get("state", {}).get("current_action", "")[:160].replace("\n", " ")
    with open(paths.EVENTS_LOG, "a", encoding="utf-8") as f:
        f.write(f"{wrapper['logged_at']} | R{state['round']} | seq{seq} | {wrapper['hash'][:16]} | {digest}\n")
    if flag:
        sys.stderr.write(
            "⚠️  GOVERNANCE FLAG: task.status set to a terminal state by the agent itself.\n"
            "    Recorded, not blocked. Completion is the operator's stamp, not the agent's claim.\n")
    return wrapper


def verify() -> bool:
    rounds = read_rounds()
    prev = "0" * 64
    ok = True
    for i, w in enumerate(rounds, 1):
        if w.get("prev_hash") != prev:
            print(f"❌ line {i} (seq {w.get('seq')}): prev_hash does not match previous round")
            ok = False
        want = chain_hash(prev, w["state"])
        if w.get("hash") != want:
            print(f"❌ line {i} (seq {w.get('seq')}): hash mismatch\n   stored   {w.get('hash')}\n   computed {want}")
            ok = False
        prev = w.get("hash", prev)
    print(("✅ chain intact" if ok else "❌ chain BROKEN") + f" — {len(rounds)} rounds")
    return ok


def anchor_line(w: dict) -> str:
    """Canonical anchor an agent can print at the end of a reply (see ledger/anchor.py)."""
    return f"⚓ R{w['state']['round']} · seq{w['seq']} · {w['hash'][:16]}"


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "append":
        raw = sys.stdin.read() if (len(a) < 2 or a[1] == "-") else open(a[1], encoding="utf-8").read()
        try:
            state = json.loads(raw)
            w = append(state)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"❌ {e}", file=sys.stderr); sys.exit(2)
        print(f"✓ appended seq={w['seq']} round={state['round']} hash={w['hash'][:16]}")
        print(anchor_line(w))
        sys.exit(0)
    if a[0] == "verify":
        sys.exit(0 if verify() else 1)
    if a[0] == "tail":
        n = int(a[1]) if len(a) > 1 else 5
        for w in read_rounds()[-n:]:
            print(f"seq{w['seq']:>5} R{w['state']['round']:<5} {w['logged_at']} {w['hash'][:16]}  "
                  f"{w['state'].get('state', {}).get('context', '')[:60]}")
        sys.exit(0)
    if a[0] == "current":
        print(paths.STATE_CURRENT.read_text(encoding="utf-8") if paths.STATE_CURRENT.exists() else "{}")
        sys.exit(0)
    print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
