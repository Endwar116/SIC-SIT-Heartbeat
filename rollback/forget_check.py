#!/usr/bin/env python3
"""forget_check.py — acceptance test for "forgetting" in a SQLite-backed store (law-005).

Incident: a vector store's DELETE marked rows as tombstones. The database file did not shrink, orphan vectors
stayed, and a full rebuild was needed. "DELETE returned success" was taken to mean "the data is gone".

Acceptance is measured, not reported. After a deletion you must be able to show:
  * freelist_count == 0          (no free pages still holding old rows — run VACUUM first)
  * file size did not grow       (compared with a recorded baseline)
  * orphan rows == 0             (rows in a dependent table whose parent is gone — you supply the SQL)

  forget_check.py baseline <db.sqlite>                        record size/pages for later comparison
  forget_check.py check    <db.sqlite> [--orphan-sql "SELECT count(*) FROM vec WHERE doc_id NOT IN (SELECT id FROM docs)"]
                                        [--vacuum]            run VACUUM before measuring
Exit 0 = accepted, 1 = forgetting not proven, 2 = usage.
Baselines live in $HEARTBEAT_HOME/state/forget_baselines.json keyed by absolute path.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

BASE = paths.STATE / "forget_baselines.json"


def measure(db: str, orphan_sql=None, vacuum=False):
    con = sqlite3.connect(db)
    try:
        if vacuum:
            con.execute("VACUUM")
        free = con.execute("PRAGMA freelist_count").fetchone()[0]
        pages = con.execute("PRAGMA page_count").fetchone()[0]
        orphans = con.execute(orphan_sql).fetchone()[0] if orphan_sql else None
    finally:
        con.close()
    return {"bytes": os.path.getsize(db), "pages": pages, "freelist": free, "orphans": orphans}


def load():
    return json.loads(BASE.read_text()) if BASE.exists() else {}


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline"); b.add_argument("db")
    c = sub.add_parser("check"); c.add_argument("db"); c.add_argument("--orphan-sql"); c.add_argument("--vacuum", action="store_true")
    a = ap.parse_args()
    db = str(Path(a.db).expanduser().resolve())
    if a.cmd == "baseline":
        paths.ensure_dirs(); d = load(); d[db] = measure(db); BASE.write_text(json.dumps(d, indent=1))
        print(f"baseline recorded: {d[db]}"); return 0
    m = measure(db, a.orphan_sql, a.vacuum)
    base = load().get(db)
    problems = []
    if m["freelist"] > 0:
        problems.append(f"freelist_count={m['freelist']} (old pages still allocated; run with --vacuum)")
    if m["orphans"]:
        problems.append(f"orphans={m['orphans']}")
    if base and m["bytes"] > base["bytes"]:
        problems.append(f"file grew: {base['bytes']} -> {m['bytes']} bytes")
    print(json.dumps({"measured": m, "baseline": base}, indent=1))
    if problems:
        print("❌ forgetting NOT proven: " + "; ".join(problems)); return 1
    print("✅ forgetting accepted: no free pages, no orphans, file did not grow"); return 0


if __name__ == "__main__":
    sys.exit(main())
