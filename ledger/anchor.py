#!/usr/bin/env python3
"""anchor.py — the one-line anchor that joins a transcript to the ledger.

Format (frozen):   ⚓ R<round> · seq<n> · <hash16>
  * the emoji is for human eyes only and is never a search key
  * digits are half-width ASCII; hash is 16 lowercase hex chars
  * the separator is " · " (U+00B7 with spaces) — tools accept drift, but only this form is canonical

Why freeze it: in a real archive, 16% of hand-written anchors had drifted (full-width digits,
"|" separators, uppercase hex, missing emoji). Retrieval tools still found them via the ledger,
but the anchor→ledger join broke. Drift is measured here, not assumed.

  anchor.py emit <round>          canonical line for a round already in the ledger
  anchor.py check <file...>       report drifted anchors (exit 1 if any)
  anchor.py fix <file...>         rewrite drifted anchors in place (.bak kept)
  anchor.py coverage <file...>    % of ledger rounds that appear as an anchor in the given files
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import read_rounds  # noqa: E402

LOOSE = re.compile(r"(⚓\s*)?[RＲ]([0-9０-９]+)\s*[·|.｜･・]\s*seq([0-9０-９]+)\s*[·|.｜･・]\s*([0-9a-fA-F]{8,16})")
STRICT = re.compile(r"^⚓ R(\d+) · seq(\d+) · ([0-9a-f]{16})$")
FW2HW = str.maketrans("０１２３４５６７８９Ｒ", "0123456789R")


def canon(r, s, h): return f"⚓ R{r} · seq{s} · {h}"


def normalize(m):
    r = int(m.group(2).translate(FW2HW)); s = int(m.group(3).translate(FW2HW)); h = m.group(4).lower()
    return canon(r, s, h), r


def scan(text):
    return [(m.group(0), *normalize(m), bool(STRICT.match(m.group(0)))) for m in LOOSE.finditer(text)]


def cmd_check(files, fix=False):
    drift = 0
    for p in files:
        try:
            text = open(p, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        found = scan(text)
        bad = [(a, b) for a, b, _, ok in found if not ok]
        if found:
            print(f"{p}: {len(found)} anchors, {len(bad)} drifted")
        for a, b in bad[:5]:
            print(f"   {a!r} -> {b!r}")
        drift += len(bad)
        if fix and bad:
            if not os.path.exists(p + ".bak"):
                os.replace(p, p + ".bak")
                text = open(p + ".bak", encoding="utf-8").read()
            open(p, "w", encoding="utf-8").write(LOOSE.sub(lambda m: normalize(m)[0], text))
            print("   fixed (backup .bak)")
    print(f"total drift: {drift}")
    return 0 if (drift == 0 or fix) else 1


def cmd_emit(rnd):
    for w in read_rounds():
        if w["state"]["round"] == int(rnd):
            print(canon(w["state"]["round"], w["seq"], w["hash"][:16])); return 0
    print(f"❌ round {rnd} not in ledger", file=sys.stderr); return 2


def cmd_coverage(files):
    rounds = {w["state"]["round"] for w in read_rounds()}
    seen, total, drifted = set(), 0, 0
    for p in files:
        try:
            text = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for _, _, r, ok in scan(text):
            total += 1; seen.add(r); drifted += (not ok)
    hit = len(seen & rounds)
    print(f"ledger rounds     {len(rounds)}\nanchored          {hit}\ncoverage          {hit / len(rounds) * 100 if rounds else 0:.1f}%")
    print(f"anchor lines      {total} (drifted {drifted} = {drifted / total * 100 if total else 0:.0f}%)")
    return 0


def main():
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(2)
    if a[0] == "emit" and len(a) > 1: sys.exit(cmd_emit(a[1]))
    if a[0] in ("check", "fix") and len(a) > 1: sys.exit(cmd_check(a[1:], fix=(a[0] == "fix")))
    if a[0] == "coverage" and len(a) > 1: sys.exit(cmd_coverage(a[1:]))
    print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
