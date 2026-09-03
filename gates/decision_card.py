#!/usr/bin/env python3
"""decision_card.py — decisions escalated to a human must be answerable without lookup.

Incident behind this gate: an operator with delegated authority to an agent found 21 open
decision cards waiting for them, each assuming they remembered the thread, knew the codenames,
and could look things up. Their words: "I keep not knowing which thing you mean. I don't have
the capacity to go and find out." Every card was individually well-formed. Together they were
unanswerable. The old rule ("four sections") guaranteed sections, not answerability.

Rule — five elements, no exceptions, and at most THREE open cards at once:
  1 WHAT THIS IS      two sentences that reconstruct the situation for someone who forgot everything.
                      No codename as subject. No "see file X". No "as mentioned".
  2 WHY YOU DECIDE    name which reserved category this falls in (money/external, people,
                      irreversible, operator-reserved). Not in a reserved category => the card
                      should not exist: decide it yourself and leave a receipt.
  3 OPTIONS           each answerable with one word; each with its meaning spelled out.
  4 IF YOU DON'T      the default outcome. Silence must never deadlock the system.
  5 RECOMMENDATION    one option + one sentence. "Either is fine" is forbidden.

Emphasis (the operator's words: "what should be loud, make it loud, or I cannot see how to choose"):
  E1 the first line under the card heading is a bold one-glance summary (**…**) of the choice
  E2 every option word in the options table is bold
  E3 the recommendation names one option word, bold, exactly as it appears in the table
A card that has all five elements but buries the choice in plain text fails E1–E3.

Usage:  decision_card.py card <file>  |  board <file>  |  rules
"""
import re
import sys

REQUIRED = [
    ("WHAT THIS IS", r"what this is|這是哪件事|background|背景"),
    ("WHY YOU DECIDE", r"why (you|only you)|為什麼(只有你|是你)|reserved|四類|irreversible|不可逆"),
    ("OPTIONS", r"\|\s*(reply|回)\s*\||options|選項|one word|一個字"),
    ("IF YOU DON'T", r"if you don'?t|default|不回會怎樣|預設"),
    ("RECOMMENDATION", r"recommend|建議"),
]
BARE_CODE = re.compile(r"\b(?:[A-Z]{1,4}-\d{2,4}|R\d{3,}|seq\d+)\b")
GLOSS = re.compile(r"[（(=＝]|i\.e\.|that is|就是|意思是")
CARD_HEAD = re.compile(r"^###?\s*(?:card|卡)\s*\d", re.M | re.I)
MAX_OPEN = 3


def emphasis_problems(text):
    bad = []
    body = text.strip().split("\n", 1)
    first = (body[1].strip().split("\n", 1)[0] if len(body) > 1 else "").strip() if text.lstrip().startswith("#") else body[0].strip()
    # E1: first non-empty line after heading is bold
    lines = [l for l in text.split("\n")[1:] if l.strip()]
    if not lines or not re.match(r"^\*\*.+\*\*", lines[0].strip()):
        bad.append("E1 first line under heading is not a bold one-glance summary")
    # E2: option words bold
    opts = re.findall(r"^\|\s*(.+?)\s*\|", text, re.M)
    opts = [o for o in opts if o and not re.match(r"^(reply|回|-+|:?-+:?)$", o.strip(), re.I)]
    plain = [o for o in opts if not re.match(r"^\*\*.+\*\*$", o.strip())]
    if opts and plain:
        bad.append(f"E2 option words not bold: {plain[:3]}")
    # E3: recommendation contains a bold option word that matches the table
    # the recommendation line: prefer a line that STARTS with bold Recommendation/建議; else the last line
    # containing the keyword (the one-glance line may also contain it)
    cands = re.findall(r"^[^\n]*(?:recommend|建議)[^\n]*$", text, re.I | re.M)
    pref = [c for c in cands if re.match(r"^\s*\*\*(?:recommendation|我?建議)", c, re.I)]
    rec = re.match(r".*", (pref or cands or [""])[-1])
    if rec:
        bold_in_rec = set(re.findall(r"\*\*(.+?)\*\*", rec.group(0)))
        table_words = {o.strip("* ") for o in opts}
        if not (bold_in_rec & table_words):
            bad.append("E3 recommendation does not bold one option word from the table")
    return bad


def check_card(text, label="card"):
    bad = [f"missing [{n}]" for n, pat in REQUIRED if not re.search(pat, text, re.I)]
    bad += emphasis_problems(text)
    bares = sorted({m.group(0) for m in BARE_CODE.finditer(text)
                    if not GLOSS.search(text[max(0, m.start() - 30):m.end() + 40])})
    if bares:
        bad.append("unexplained codenames: " + ", ".join(bares[:5]))
    if re.search(r"(see|詳見)\s*[`/]|as (mentioned|discussed) (above|before)|如前所述", text, re.I):
        bad.append("sends the reader to another file (a card must be self-sufficient)")
    if bad:
        print(f"❌ {label}:"); [print(f"     {b}") for b in bad]; return False
    print(f"✅ {label}: five elements present, no bare codenames, self-sufficient"); return True


def main():
    a = sys.argv[1:]
    if not a or a[0] == "rules":
        print(__doc__); sys.exit(0)
    if len(a) < 2:
        print(__doc__); sys.exit(2)
    text = open(a[1], encoding="utf-8").read()
    if a[0] == "card":
        sys.exit(0 if check_card(text) else 1)
    if a[0] == "board":
        head = re.split(r"^##\s*(?:§2|receipts|收據)", text, flags=re.M | re.I)[0]
        blocks = CARD_HEAD.split(head)[1:]
        print(f"open cards: {len(blocks)} (max {MAX_OPEN})")
        ok = len(blocks) <= MAX_OPEN
        if not ok:
            print(f"❌ over the limit — decide the rest yourself or queue them")
        for i, b in enumerate(blocks, 1):
            ok = check_card(b, f"card {i}") and ok
        sys.exit(0 if ok else 1)
    print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
