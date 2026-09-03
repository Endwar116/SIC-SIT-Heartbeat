#!/usr/bin/env python3
"""zombie.py — pending items that outlived their TTL.

state/pending.jsonl: one JSON per line {"id","title","owner","opened","ttl_days"}; a later line
with the same id and "closed": {...} closes it. Append-only; nothing is edited in place.

  zombie.py check            list items past TTL (exit 1 if any)
  zombie.py open <id> <title> [--owner X] [--ttl 7]
  zombie.py close <id> --receipt "<what proves it is done>"
Closing requires a receipt. "Done" without evidence is the disease this whole repo treats.
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402


def load():
    items = {}
    if not paths.PENDING.exists():
        return items
    for line in open(paths.PENDING, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "closed" in r:
            items.get(r["id"], {}).update(closed=r["closed"])
        else:
            items[r["id"]] = r
    return items


def append(obj):
    paths.ensure_dirs()
    with open(paths.PENDING, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    o = sub.add_parser("open"); o.add_argument("id"); o.add_argument("title"); o.add_argument("--owner", default="agent"); o.add_argument("--ttl", type=int, default=7)
    c = sub.add_parser("close"); c.add_argument("id"); c.add_argument("--receipt", required=True)
    a = ap.parse_args()
    if a.cmd == "open":
        append({"id": a.id, "title": a.title, "owner": a.owner, "opened": date.today().isoformat(), "ttl_days": a.ttl}); print("opened", a.id); return 0
    if a.cmd == "close":
        append({"id": a.id, "closed": {"at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "receipt": a.receipt}}); print("closed", a.id); return 0
    items = load(); today = date.today(); zombies = []
    for it in items.values():
        if it.get("closed"):
            continue
        age = (today - date.fromisoformat(it["opened"])).days
        if age > it.get("ttl_days", 7):
            zombies.append((it["id"], age, it.get("owner"), it["title"]))
    open_n = sum(1 for i in items.values() if not i.get("closed"))
    print(f"open {open_n}, past TTL {len(zombies)}")
    for i, age, owner, title in sorted(zombies, key=lambda z: -z[1]):
        print(f"  {i:<8} {age:>3}d  owner={owner:<10} {title[:70]}")
    return 1 if zombies else 0


if __name__ == "__main__":
    sys.exit(main())
