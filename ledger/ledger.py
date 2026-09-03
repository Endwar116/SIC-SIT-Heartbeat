#!/usr/bin/env python3
"""ledger.py — append-only, hash-chained ledger of SIC-JS 4.0 rounds.

Ledger format version 2 (after adversarial review of v1):
  * one round = one JSON line ("wrapper"):
        {"ledger_version": 2, "seq", "logged_at", "hash", "prev_hash", "state": <SIC-JS block>, ["discontinuity"], ["governance_flag"]}
  * hash = sha256(canonical(wrapper without "hash")) — seq, logged_at, prev_hash and state are all covered.
    v1 wrappers (no ledger_version) are still verified with the v1 rule sha256(prev_hash + canonical(state)).
  * canonical = json.dumps(sort_keys, ensure_ascii=False, compact separators, allow_nan=False); strings NFC-normalised on ingest.
    These exact Python rules are normative (docs/SPEC_LEDGER.md).
  * appends hold an exclusive flock for the whole read→append→state→events sequence; file and directory are fsynced.
  * continuity is enforced on append: round == prev.round + 1 and entity.name unchanged, unless
    --allow-discontinuity "<reason>" is given (the reason is written into the wrapper).
  * STATE_CURRENT.json = {"seq","hash","state"} and `verify` cross-checks it against the last round.
  * a torn final line (crash mid-write) is detected; `repair --torn-tail` moves the fragment aside — the only
    sanctioned modification of the file, and it is logged.
  * governance: an agent marking its own task completed/dismissed/archived is recorded with governance_flag.

CLI:  append - [--auto-round] [--allow-discontinuity R]  |  verify  |  tail [n]  |  current  |  repair --torn-tail
Exit: 0 ok | 1 verification failed / torn tail | 2 usage or validation error
"""
import fcntl
import hashlib
import json
import math
import os
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

LEDGER_VERSION = 2
SELF_CLOSE_STATES = {"completed", "dismissed", "archived"}
REQUIRED_TOP = ("sic_version", "round", "entity", "state", "relation", "event", "intent")
ENTITY_WINDOW = 20


class TornTail(Exception):
    pass


def nfc(obj):
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [nfc(x) for x in obj]
    if isinstance(obj, dict):
        return {nfc(k): nfc(v) for k, v in obj.items()}
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError("non-finite float in state")
    return obj


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def wrapper_hash(w: dict) -> str:
    if w.get("ledger_version", 1) >= 2:
        return sha(canonical({k: v for k, v in w.items() if k != "hash"}))
    return sha(w.get("prev_hash", "") + canonical(w["state"]))   # v1 rule


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_rounds(strict=True):
    """Parse rounds.jsonl. A final line that is unparseable AND lacks a trailing newline is a torn tail."""
    if not paths.ROUNDS.exists():
        return []
    raw = paths.ROUNDS.read_bytes()
    out = []
    lines = raw.split(b"\n")
    trailing_nl = raw.endswith(b"\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            last = (i == len(lines) - 1) or (i == len(lines) - 2 and lines[-1] == b"")
            if last and not trailing_nl:
                if strict:
                    raise TornTail(f"torn final line ({len(line)} bytes). Run: ledger.py repair --torn-tail")
                return out
            raise SystemExit(f"ledger corrupt at line {i + 1}: not JSON")
    return out


def validate_state(state):
    if not isinstance(state, dict):
        raise ValueError("state block must be an object")
    missing = [k for k in REQUIRED_TOP if k not in state]
    if missing:
        raise ValueError(f"SIC-JS block missing required top-level keys: {missing}")
    r = state.get("round")
    if not isinstance(r, int) or isinstance(r, bool):
        raise ValueError("round must be an integer")
    for k in ("entity", "state", "relation", "event", "intent"):
        if not isinstance(state.get(k), dict):
            raise ValueError(f"{k} must be an object")
    if "task" in state and state["task"] is not None and not isinstance(state["task"], dict):
        raise ValueError("task must be an object or absent")
    st = (state.get("task") or {}).get("status")
    return "AI_SELF_CLOSED" if st in SELF_CLOSE_STATES else None


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class locked:
    def __init__(self):
        paths.ensure_dirs()
        self.fd = os.open(str(paths.ROUNDS) + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    def __enter__(self):
        fcntl.flock(self.fd, fcntl.LOCK_EX); return self
    def __exit__(self, *a):
        fcntl.flock(self.fd, fcntl.LOCK_UN); os.close(self.fd)


def append(state: dict, allow_discontinuity: str = None, auto_round: bool = False) -> dict:
    """auto_round=True: set state.round and relation.upstream from the ledger *inside the lock*. Use it when
    several writers may append concurrently (a Monitor loop + cron + an interactive agent). Without it a stale
    round fails closed with exit 2 — never a corrupted chain."""
    state = nfc(state)
    flag = validate_state(state)
    with locked():
        rounds = read_rounds()          # raises TornTail — never append onto a torn file
        prev = rounds[-1] if rounds else None
        if auto_round:
            state["round"] = (prev["state"]["round"] + 1) if prev else 1
            state.setdefault("relation", {})["upstream"] = prev["hash"][:16] if prev else None
        prev_hash = prev["hash"] if prev else "0" * 64
        seq = (prev["seq"] + 1) if prev else 1
        problems = []
        if prev:
            if state["round"] != prev["state"]["round"] + 1:
                problems.append(f"round {state['round']} does not follow {prev['state']['round']}")
            if state["entity"].get("name") != prev["state"]["entity"].get("name"):
                problems.append(f"entity.name changed: {prev['state']['entity'].get('name')!r} -> {state['entity'].get('name')!r}")
        if problems and not allow_discontinuity:
            raise ValueError("continuity: " + "; ".join(problems) + "  (use --allow-discontinuity \"<reason>\" to record a deliberate break)")
        w = {"ledger_version": LEDGER_VERSION, "seq": seq, "logged_at": now_iso(), "prev_hash": prev_hash, "state": state}
        if problems:
            w["discontinuity"] = {"reason": allow_discontinuity, "problems": problems}
        if flag:
            w["governance_flag"] = flag
        w["hash"] = wrapper_hash(w)
        line = json.dumps(w, ensure_ascii=False) + "\n"
        with open(paths.ROUNDS, "a", encoding="utf-8") as f:
            f.write(line); f.flush(); os.fsync(f.fileno())
        dfd = os.open(str(paths.LEDGER_DIR), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        atomic_write(paths.STATE_CURRENT, json.dumps({"seq": seq, "hash": w["hash"], "state": state}, ensure_ascii=False, indent=1))
        digest = str(state.get("state", {}).get("current_action", ""))[:160].replace("\n", " ")
        with open(paths.EVENTS_LOG, "a", encoding="utf-8") as f:
            f.write(f"{w['logged_at']} | R{state['round']} | seq{seq} | {w['hash'][:16]} | {digest}\n")
    if flag:
        sys.stderr.write("⚠️  GOVERNANCE FLAG: task.status set to a terminal state by the agent itself. "
                         "Recorded, not blocked. Completion is the operator's stamp, not the agent's claim.\n")
    if problems:
        sys.stderr.write(f"⚠️  DISCONTINUITY recorded: {'; '.join(problems)} — reason: {allow_discontinuity}\n")
    return w


def verify() -> bool:
    try:
        rounds = read_rounds()
    except TornTail as e:
        print(f"❌ {e}"); return False
    ok = True
    prev_hash, prev_round, names = "0" * 64, None, []
    for i, w in enumerate(rounds, 1):
        if w.get("prev_hash") != prev_hash:
            print(f"❌ seq {w.get('seq')} (line {i}): prev_hash does not match previous round"); ok = False
        if w.get("hash") != wrapper_hash(w):
            print(f"❌ seq {w.get('seq')} (line {i}): hash mismatch"); ok = False
        if w.get("seq") != i:
            print(f"❌ line {i}: seq is {w.get('seq')}, expected {i}"); ok = False
        r = w["state"].get("round")
        if prev_round is not None and r != prev_round + 1 and "discontinuity" not in w:
            print(f"❌ seq {w.get('seq')}: round {r} does not follow {prev_round} and no discontinuity is recorded"); ok = False
        names.append(w["state"].get("entity", {}).get("name"))
        prev_hash, prev_round = w.get("hash", prev_hash), r
    if len(set(names[-ENTITY_WINDOW:])) > 1:
        print(f"❌ entity.name changed within the last {ENTITY_WINDOW} rounds: {sorted(set(n for n in names[-ENTITY_WINDOW:] if n))}"); ok = False
    if rounds and paths.STATE_CURRENT.exists():
        try:
            cur = json.loads(paths.STATE_CURRENT.read_text(encoding="utf-8"))
            if cur.get("hash") != rounds[-1]["hash"]:
                print("❌ STATE_CURRENT.json does not match the last round (desync or a deleted trailing line)"); ok = False
        except (OSError, json.JSONDecodeError):
            print("❌ STATE_CURRENT.json unreadable"); ok = False
    print(("✅ chain intact" if ok else "❌ chain BROKEN") + f" — {len(rounds)} rounds")
    return ok


def repair_torn_tail() -> bool:
    with locked():
        try:
            read_rounds(); print("no torn tail"); return True
        except TornTail:
            pass
        raw = paths.ROUNDS.read_bytes()
        cut = raw.rfind(b"\n") + 1
        frag = raw[cut:]
        tdir = paths.LEDGER_DIR / "torn"; tdir.mkdir(exist_ok=True)
        fp = tdir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.fragment"
        fp.write_bytes(frag)
        atomic_write(paths.ROUNDS, raw[:cut].decode("utf-8"))
        with open(paths.EVENTS_LOG, "a", encoding="utf-8") as f:
            f.write(f"{now_iso()} | REPAIR | torn tail ({len(frag)} bytes) moved to {fp.name}\n")
        print(f"✅ torn tail ({len(frag)} bytes) moved to {fp}; ledger is appendable again")
        return True


def anchor_line(w: dict) -> str:
    return f"⚓ R{w['state']['round']} · seq{w['seq']} · {w['hash'][:16]}"


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    try:
        if a[0] == "append":
            src = a[1] if len(a) > 1 and a[1] != "-" and not a[1].startswith("--") else "-"
            reason = a[a.index("--allow-discontinuity") + 1] if "--allow-discontinuity" in a else None
            raw = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
            state = json.loads(raw)
            w = append(state, reason, auto_round=("--auto-round" in a))
            print(f"✓ appended seq={w['seq']} round={state['round']} hash={w['hash'][:16]}")
            print(anchor_line(w)); sys.exit(0)
        if a[0] == "verify":
            sys.exit(0 if verify() else 1)
        if a[0] == "repair" and "--torn-tail" in a:
            sys.exit(0 if repair_torn_tail() else 1)
        if a[0] == "tail":
            n = int(a[1]) if len(a) > 1 else 5
            for w in read_rounds(strict=False)[-n:]:
                print(f"seq{w['seq']:>5} R{w['state']['round']:<5} {w['logged_at']} {w['hash'][:16]}  {str(w['state'].get('state', {}).get('context', ''))[:60]}")
            sys.exit(0)
        if a[0] == "current":
            print(paths.STATE_CURRENT.read_text(encoding="utf-8") if paths.STATE_CURRENT.exists() else "{}"); sys.exit(0)
        print(__doc__); sys.exit(2)
    except TornTail as e:
        print(f"❌ {e}", file=sys.stderr); sys.exit(1)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        print(f"❌ {e.__class__.__name__}: {e}", file=sys.stderr); sys.exit(2)


if __name__ == "__main__":
    main()
