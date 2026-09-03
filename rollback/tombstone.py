#!/usr/bin/env python3
"""tombstone.py — soft delete with a paper trail, and the way back.

Every "delete" in this system is:  move into TRASH/<date>_<name>/  +  write TOMBSTONE.md
The tombstone answers, without the agent's memory: who, when, why, what was moved, how to undo.
Restore = move it back. Nothing is destroyed until a HUMAN empties the trash (never the agent).

  tombstone.py trash <path> --why "<one line>" [--by <actor>]
  tombstone.py restore <trash-entry-dir>
  tombstone.py list
  tombstone.py verify <trash-entry-dir>        # sha256 manifest still matches
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(root: Path):
    out = {}
    if root.is_file():
        return {root.name: sha_file(root)}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = sha_file(p)
    return out


def trash(src: str, why: str, by: str):
    s = Path(src).expanduser().resolve()
    if not s.exists():
        sys.exit(f"❌ {s} does not exist")
    paths.ensure_dirs()
    ts = datetime.now(timezone.utc).astimezone()
    entry = paths.TRASH / f"{ts.strftime('%Y-%m-%d_%H%M%S')}_{s.name}"
    entry.mkdir(parents=True)
    man = manifest(s)
    dest = entry / s.name
    shutil.move(str(s), str(dest))
    (entry / "MANIFEST.sha256.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    (entry / "TOMBSTONE.md").write_text(f"""# Tombstone

- **what**: `{s}`
- **moved to**: `{dest}`
- **when**: {ts.isoformat(timespec='seconds')}
- **by**: {by}
- **why**: {why}
- **files**: {len(man)}  (sha256 manifest alongside)
- **restore**: `python3 rollback/tombstone.py restore "{entry}"`
- **policy**: nothing here is destroyed by an agent. A human empties the trash after 30 days.
""", encoding="utf-8")
    print(f"✅ moved to trash: {entry}\n   restore with: tombstone.py restore \"{entry}\"")
    return entry


def restore(entry: str):
    e = Path(entry).expanduser().resolve()
    tomb = e / "TOMBSTONE.md"
    if not tomb.exists():
        sys.exit(f"❌ not a trash entry (no TOMBSTONE.md): {e}")
    orig = None
    for line in tomb.read_text(encoding="utf-8").splitlines():
        if line.startswith("- **what**:"):
            orig = Path(line.split("`")[1])
    if not orig:
        sys.exit("❌ tombstone has no original path")
    payload = [p for p in e.iterdir() if p.name not in ("TOMBSTONE.md", "MANIFEST.sha256.json")]
    if len(payload) != 1:
        sys.exit(f"❌ expected exactly one payload in {e}, found {len(payload)}")
    if orig.exists():
        sys.exit(f"❌ {orig} already exists — refusing to overwrite; move it aside first")
    orig.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(payload[0]), str(orig))
    (e / "RESTORED.md").write_text(f"restored to `{orig}` at {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}\n",
                                   encoding="utf-8")
    print(f"✅ restored -> {orig}")


def verify(entry: str) -> bool:
    e = Path(entry).expanduser().resolve()
    want = json.loads((e / "MANIFEST.sha256.json").read_text(encoding="utf-8"))
    payload = [p for p in e.iterdir() if p.name not in ("TOMBSTONE.md", "MANIFEST.sha256.json", "RESTORED.md")]
    if not payload:
        print("(payload already restored)"); return True
    got = manifest(payload[0])
    ok = want == got
    print("✅ manifest matches" if ok else f"❌ manifest mismatch: {set(want) ^ set(got) or 'content changed'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trash"); t.add_argument("path"); t.add_argument("--why", required=True); t.add_argument("--by", default=paths.AGENT_NAME)
    r = sub.add_parser("restore"); r.add_argument("entry")
    v = sub.add_parser("verify"); v.add_argument("entry")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "trash": trash(a.path, a.why, a.by)
    elif a.cmd == "restore": restore(a.entry)
    elif a.cmd == "verify": sys.exit(0 if verify(a.entry) else 1)
    elif a.cmd == "list":
        paths.ensure_dirs()
        for e in sorted(paths.TRASH.iterdir()):
            if (e / "TOMBSTONE.md").exists():
                print(("♻️ " if (e / "RESTORED.md").exists() else "🗑 ") + e.name)


if __name__ == "__main__":
    main()
