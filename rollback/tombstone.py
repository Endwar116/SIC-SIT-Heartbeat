#!/usr/bin/env python3
"""tombstone.py — soft delete with a paper trail, and the way back.

Every "delete" is:  move into TRASH/<stamp>_<name>/  +  tombstone.json (machine truth)  +  TOMBSTONE.md (rendered).
Restore reads ONLY tombstone.json. Nothing is destroyed until a HUMAN empties the trash.

v2 (after adversarial review): restore used to parse the markdown, so a crafted --why could redirect a
restore to an attacker-chosen path; symlinks were resolved and their targets trashed; two trashes of the
same name within a second collided; the manifest was never re-verified after the move.
  * metadata lives in tombstone.json; --why may not contain newlines or backticks
  * symlinks are refused (trash the target explicitly if that is what you mean)
  * entry names carry microseconds + a counter
  * after the move the manifest is recomputed and compared; mismatch aborts loudly

  tombstone.py trash <path> --why "<one line>" [--by <actor>]
  tombstone.py restore <trash-entry-dir>
  tombstone.py list | verify <trash-entry-dir>
"""
import argparse
import hashlib
import json
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
    if root.is_file():
        return {root.name: sha_file(root)}
    return {str(p.relative_to(root)): sha_file(p) for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def unique_entry(base: Path, name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    for n in range(1000):
        e = base / (f"{ts}_{name}" if n == 0 else f"{ts}_{name}.{n}")
        if not e.exists():
            return e
    raise SystemExit("❌ could not allocate a unique trash entry")


def trash(src: str, why: str, by: str):
    if "\n" in why or "`" in why:
        sys.exit("❌ --why must be one line without backticks")
    s = Path(src).expanduser().absolute()
    if s.is_symlink():
        sys.exit(f"❌ {s} is a symlink → refusing (would you trash the link or its target? say which explicitly)")
    if not s.exists():
        sys.exit(f"❌ {s} does not exist")
    paths.ensure_dirs()
    entry = unique_entry(paths.TRASH, s.name); entry.mkdir(parents=True)
    man_before = manifest(s)
    dest = entry / s.name
    shutil.move(str(s), str(dest))
    man_after = manifest(dest)
    if man_after != man_before:
        sys.exit(f"❌ manifest changed during move ({len(set(man_before) ^ set(man_after))} paths differ) — investigate {entry}")
    meta = {"what": str(s), "moved_to": str(dest), "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "by": by, "why": why, "files": len(man_after), "manifest": man_after, "restored": None}
    (entry / "tombstone.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (entry / "TOMBSTONE.md").write_text(
        f"# Tombstone\n\n- **what**: `{s}`\n- **when**: {meta['when']}\n- **by**: {by}\n- **why**: {why}\n"
        f"- **files**: {meta['files']} (sha256 manifest in tombstone.json)\n"
        f"- **restore**: `python3 rollback/tombstone.py restore \"{entry}\"`\n"
        f"- **policy**: nothing here is destroyed by an agent; a human empties the trash after 30 days.\n", encoding="utf-8")
    print(f"✅ moved to trash: {entry}\n   restore with: tombstone.py restore \"{entry}\"")
    return entry


def load_meta(entry: Path):
    mj = entry / "tombstone.json"
    if not mj.exists():
        sys.exit(f"❌ not a trash entry (no tombstone.json): {entry}")
    return json.loads(mj.read_text(encoding="utf-8")), mj


def restore(entry: str):
    e = Path(entry).expanduser().absolute()
    meta, mj = load_meta(e)
    if meta.get("restored"):
        sys.exit(f"❌ already restored at {meta['restored']}")
    orig, payload = Path(meta["what"]), Path(meta["moved_to"])
    if not payload.exists():
        sys.exit(f"❌ payload missing: {payload}")
    if manifest(payload) != meta["manifest"]:
        sys.exit("❌ payload manifest does not match tombstone.json — refusing to restore tampered content")
    if orig.exists():
        sys.exit(f"❌ {orig} already exists — refusing to overwrite; move it aside first")
    orig.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(payload), str(orig))
    meta["restored"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mj.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ restored -> {orig}")


def verify(entry: str) -> bool:
    e = Path(entry).expanduser().absolute(); meta, _ = load_meta(e)
    if meta.get("restored"):
        print("(payload already restored)"); return True
    ok = manifest(Path(meta["moved_to"])) == meta["manifest"]
    print("✅ manifest matches" if ok else "❌ manifest mismatch"); return ok


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trash"); t.add_argument("path"); t.add_argument("--why", required=True); t.add_argument("--by", default=paths.AGENT_NAME)
    r = sub.add_parser("restore"); r.add_argument("entry")
    v = sub.add_parser("verify"); v.add_argument("entry"); sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "trash": trash(a.path, a.why, a.by)
    elif a.cmd == "restore": restore(a.entry)
    elif a.cmd == "verify": sys.exit(0 if verify(a.entry) else 1)
    elif a.cmd == "list":
        paths.ensure_dirs()
        for e in sorted(paths.TRASH.iterdir()):
            if (e / "tombstone.json").exists():
                m = json.loads((e / "tombstone.json").read_text(encoding="utf-8"))
                print(("♻️ " if m.get("restored") else "🗑 ") + e.name + f"  ← {m['what']}")


if __name__ == "__main__":
    main()
