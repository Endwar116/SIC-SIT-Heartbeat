#!/usr/bin/env python3
"""legislate.py — turn an incident into a law, and keep the lineage.

The pipeline this repo exists for:  incident -> law -> gate.
A law with enforced_by.kind == "none-yet" is a debt: it is written down, but nothing fires.
`legislate.py debts` lists them so the debt stays visible.

  legislate.py new --what "..." --signal "..." --cause "..." --text "..." --check "..." [--check ...]
                   [--enforce gate|procedure|checker|none-yet --ref path] [--by name]
  legislate.py list
  legislate.py debts
  legislate.py validate <law.json>
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

SCHEMA = json.load(open(Path(__file__).resolve().parent / "LAW_SCHEMA.json", encoding="utf-8"))


def validate(doc: dict):
    problems = []
    for k in SCHEMA["required"]:
        if k not in doc:
            problems.append(f"missing {k}")
    if not re.match(r"^law-\d{3,}$", str(doc.get("id", ""))):
        problems.append("id must look like law-001")
    for k in ("when", "what", "signal"):
        if not (doc.get("incident") or {}).get(k):
            problems.append(f"incident.{k} missing")
    if not (doc.get("law") or {}).get("checks"):
        problems.append("law.checks must have at least one checkable condition")
    if (doc.get("enforced_by") or {}).get("kind") not in ("gate", "procedure", "checker", "none-yet"):
        problems.append("enforced_by.kind invalid")
    return problems


def next_id():
    paths.ensure_dirs()
    nums = [int(p.stem.split("-")[1]) for p in paths.LAWS.glob("law-*.json") if p.stem.split("-")[1].isdigit()]
    return f"law-{(max(nums) + 1) if nums else 1:03d}"


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    for f in ("what", "signal", "cause", "text"):
        n.add_argument(f"--{f}", required=True)
    n.add_argument("--check", action="append", required=True)
    n.add_argument("--enforce", default="none-yet", choices=["gate", "procedure", "checker", "none-yet"])
    n.add_argument("--ref", default=""); n.add_argument("--by", default=paths.AGENT_NAME); n.add_argument("--when", default=date.today().isoformat())
    sub.add_parser("list"); sub.add_parser("debts")
    v = sub.add_parser("validate"); v.add_argument("path")
    a = ap.parse_args()

    if a.cmd == "validate":
        p = validate(json.load(open(a.path, encoding="utf-8")))
        print("✅ valid" if not p else "❌ " + "; ".join(p)); sys.exit(0 if not p else 1)
    if a.cmd in ("list", "debts"):
        paths.ensure_dirs()
        for p in sorted(paths.LAWS.glob("law-*.json")):
            d = json.load(open(p, encoding="utf-8"))
            kind = d["enforced_by"]["kind"]
            if a.cmd == "debts" and kind != "none-yet":
                continue
            print(f"{d['id']}  [{kind:<9}] {d['law']['text'][:90]}")
        return
    lid = next_id()
    doc = {"id": lid,
           "incident": {"when": a.when, "what": a.what, "signal": a.signal},
           "root_cause": a.cause,
           "law": {"text": a.text, "checks": a.check},
           "enforced_by": {"kind": a.enforce, "ref": a.ref},
           "lineage": [f"incident:{a.when}", lid] + ([f"{a.enforce}:{a.ref}"] if a.ref else []),
           "legislated": {"by": a.by, "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}}
    probs = validate(doc)
    if probs:
        sys.exit("❌ " + "; ".join(probs))
    paths.ensure_dirs()
    (paths.LAWS / f"{lid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {lid} legislated" + ("" if a.ref else "  (enforced_by=none-yet — this is a debt; see `legislate.py debts`)"))


if __name__ == "__main__":
    main()
