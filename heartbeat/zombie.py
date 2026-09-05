#!/usr/bin/env python3
"""zombie.py — the pending ledger: work items, the pile they sit in, and whether they outlived their TTL.

state/pending.jsonl is append-only, one JSON object per line; nothing is edited in place:
  open   {"id","title","owner","opened","opened_at","ttl_days","pile","priority","cost","pre"}
  close  {"id","closed":{"at","receipt"}}      the receipt must name something a machine can check
  block  {"id","block":{"at","on","pile"}}     the blocker must be concrete; the item leaves the doable pile

Piles = who can act: doable | operator | others | conditional. An item filed as waiting must carry --pre:
what can be prepared now so that the other side's one word puts it live (false-waiting is the second idle form).

  zombie.py check                                   items past TTL (exit 1 if any)
  zombie.py open <id> <title> [--pile doable] [--priority P2] [--cost local] [--pre TEXT] [--owner X] [--ttl 7]
  zombie.py close <id> --receipt TEXT               TEXT names an existing path, a hash, an exit code or a test count
  zombie.py block <id> --on TEXT [--pile others]    TEXT is the concrete thing the item waits on
  zombie.py next                                    the top open doable item (priority, then age) as JSON; empty if none
  zombie.py snapshot                                counts per pile + sha256 over the open set (proof of emptiness)

Closing requires a receipt. "Done" without evidence is the disease this whole repo treats.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

PILES = ("doable", "operator", "others", "conditional")
PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
COSTS = ("local", "free", "cheap", "flagship")
RECEIPT_TOKENS = (r"\b[0-9a-f]{16,64}\b", r"\bsha256\b", r"\b(?:exit|rc)[:= ]?0\b", r"\bRan \d+ tests?\b",
                  r"\bHTTP[ /=]?200\b", r"\bhttp=200\b", r"\bseq=\d+")
PATH_TOKEN = re.compile(r"(?:~|\.{1,2})?/[^\s'\"`,;)]+|[\w.-]+\.(?:md|py|json|jsonl|txt|html|pdf|zip|sh|log|csv)\b")
VAGUE = {"tbd", "later", "unknown", "someone", "stuff", "things", "pending", "waiting", "soon"}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def receipt_checkable(text):
    """A receipt must name something code can verify right now. Returns (ok, why)."""
    for tok in PATH_TOKEN.findall(text or ""):
        if os.path.exists(os.path.expanduser(tok)):
            return True, f"path exists: {tok}"
    for pat in RECEIPT_TOKENS:
        if re.search(pat, text or ""):
            return True, f"token: {pat}"
    return False, "receipt names nothing a machine can check (a path that exists, a hash, an exit code, a test count)"


def concrete(reason):
    r = (reason or "").strip()
    return len(r) >= 8 and r.lower() not in VAGUE


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
        elif "block" in r:
            items.get(r["id"], {}).update(pile=r["block"].get("pile", "others"), blocker=r["block"]["on"],
                                          blocked_at=r["block"]["at"])
        else:
            r.setdefault("pile", "doable"); r.setdefault("priority", "P2"); r.setdefault("cost", "local")
            r.setdefault("opened_at", r.get("opened", ""))
            items[r["id"]] = r
    return items


def sort_key(item):
    return (PRIORITY.get(item.get("priority", "P2"), 2), item.get("opened_at", ""), item["id"])


def open_items(items=None):
    items = load() if items is None else items
    return [i for i in items.values() if not i.get("closed")]


def doable(items=None):
    return sorted([i for i in open_items(items) if i.get("pile", "doable") == "doable"], key=sort_key)


def snapshot(items=None):
    oi = open_items(items)
    counts = {p: sum(1 for i in oi if i.get("pile", "doable") == p) for p in PILES}
    canon = json.dumps(sorted((i["id"], i.get("pile", "doable"), i.get("title", "")) for i in oi), ensure_ascii=False)
    counts["sha256"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    counts["open"] = len(oi)
    return counts


def append(obj):
    paths.ensure_dirs()
    with open(paths.PENDING, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check"); sub.add_parser("next"); sub.add_parser("snapshot")
    o = sub.add_parser("open"); o.add_argument("id"); o.add_argument("title"); o.add_argument("--owner", default="agent")
    o.add_argument("--ttl", type=int, default=7); o.add_argument("--pile", default="doable", choices=PILES)
    o.add_argument("--priority", default="P2", choices=sorted(PRIORITY)); o.add_argument("--cost", default="local", choices=COSTS)
    o.add_argument("--pre", default="")
    c = sub.add_parser("close"); c.add_argument("id"); c.add_argument("--receipt", required=True)
    b = sub.add_parser("block"); b.add_argument("id"); b.add_argument("--on", required=True); b.add_argument("--pile", default="others", choices=PILES[1:])
    a = ap.parse_args()

    if a.cmd == "open":
        if a.pile != "doable" and not concrete(a.pre):
            sys.stderr.write("❌ a waiting item needs --pre: what can be prepared now so the other side's one word puts it live\n"); return 2
        if a.id in load():
            sys.stderr.write(f"❌ {a.id} already exists (append-only ledger: pick a new id)\n"); return 2
        append({"id": a.id, "title": a.title, "owner": a.owner, "opened": date.today().isoformat(), "opened_at": now_iso(),
                "ttl_days": a.ttl, "pile": a.pile, "priority": a.priority, "cost": a.cost, "pre": a.pre})
        print("opened", a.id, f"[{a.pile}/{a.priority}/{a.cost}]"); return 0
    if a.cmd == "close":
        if a.id not in load():
            sys.stderr.write(f"❌ {a.id} is not an open item\n"); return 2
        ok, why = receipt_checkable(a.receipt)
        if not ok:
            sys.stderr.write(f"❌ {why}\n"); return 2
        append({"id": a.id, "closed": {"at": now_iso(), "receipt": a.receipt}}); print("closed", a.id, "—", why); return 0
    if a.cmd == "block":
        if a.id not in load():
            sys.stderr.write(f"❌ {a.id} is not an open item\n"); return 2
        if not concrete(a.on):
            sys.stderr.write("❌ --on must name the concrete thing this item waits on (who / what / when), not a placeholder\n"); return 2
        append({"id": a.id, "block": {"at": now_iso(), "on": a.on.strip(), "pile": a.pile}}); print("blocked", a.id, "→", a.pile); return 0
    if a.cmd == "next":
        d = doable()
        if d:
            print(json.dumps({k: d[0].get(k) for k in ("id", "title", "priority", "cost", "opened", "owner")}, ensure_ascii=False))
        return 0
    if a.cmd == "snapshot":
        print(json.dumps(snapshot(), ensure_ascii=False)); return 0

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
