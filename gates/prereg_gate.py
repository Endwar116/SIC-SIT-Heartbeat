#!/usr/bin/env python3
"""prereg_gate.py — no experiment without a *sealed* pre-registration (PreToolUse: Workflow/Bash).

Incident behind this gate: the agent that wrote this had authored five versions of a
pre-registration template — then ran three benchmark rounds without sealing one. Knowing the
rule is not the same as being stopped by it.

Rule: if the command/script looks like an experiment (benchmark, control arm, gold labels,
retrieval runs, scoring...) it must reference a sealed pre-registration file that exists on
disk. Sealed means one of:
  * machine seal: prereg.json with preregistration_hash == sha256(canonical(payload))
  * sidecar:      <file>.sha256 next to the pre-registration document
  * marker:       the document itself carries FROZEN / frozen_at in its head
Escape hatch (logged): a script header line  `// PREREG-EXEMPT: <reason>`  or  `# PREREG-EXEMPT: <reason>`.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook import read_payload, block, allow, guarded  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

GATE = "prereg"
TRIGGER = re.compile(r"\b(?:benchmark|ablation|control[_ -]?arm|gold[_ -]?labels?|placebo|treatment[_ -]arm|"
                     r"retrieval[_ -](?:run|eval)|score\.py)\b.*\.(?:py|sh|json|ipynb|js)\b", re.I | re.S)
PREREG_PATH = re.compile(r"[\w/.\-]*(?:FROZEN|prereg|preregist)[\w/.\-]*\.(?:md|json)", re.I)
EXEMPT = re.compile(r"(?://|#)\s*PREREG-EXEMPT:\s*(.+)")


def sealed(path: str):
    if not os.path.exists(path):
        return False, "file does not exist"
    if path.endswith(".json"):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = None
        if isinstance(doc, dict) and doc.get("preregistration_hash"):
            want = str(doc["preregistration_hash"]).replace("sha256:", "")
            got = hashlib.sha256(json.dumps(doc.get("payload") or {}, sort_keys=True,
                                            ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            return (want == got), ("machine seal verified" if want == got else "seal BROKEN: payload was modified")
    if os.path.exists(path + ".sha256"):
        try:
            want = open(path + ".sha256", encoding="utf-8").read().split()[0]
            got = hashlib.sha256(open(path, "rb").read()).hexdigest()
            return (want == got), ("sidecar digest verified" if want == got else "sidecar digest does NOT match the document")
        except (OSError, IndexError):
            return False, "sidecar unreadable"
    try:
        head = open(path, encoding="utf-8", errors="ignore").read(4000)
    except OSError as e:
        return False, f"unreadable ({e})"
    if re.search(r"^\s*(?:>\s*)?status:\s*FROZEN\b", head, re.M | re.I):
        return True, "in-document `status: FROZEN` line"
    return False, "exists but no seal (no machine seal, no .sha256, no FROZEN marker)"


def main():
    p, problem = read_payload()
    if problem:
        allow(GATE, f"unparseable payload allowed: {problem}")
    ti = p.get("tool_input") or {}
    text = ti.get("script") or ti.get("command") or ""
    if not text and ti.get("scriptPath") and os.path.exists(ti["scriptPath"]):
        try:
            text = open(ti["scriptPath"], encoding="utf-8").read()
        except OSError:
            allow()
    if not text or not TRIGGER.search(text):
        allow()
    m = EXEMPT.search(text)
    if m:
        try:
            paths.ensure_dirs()
            with open(paths.PREREG_EXEMPTIONS, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                                    "reason": m.group(1).strip()[:200]}, ensure_ascii=False) + "\n")
        except OSError:
            pass
        allow(GATE, "exempt: " + m.group(1).strip()[:80])
    code_only = "\n".join(l for l in text.splitlines() if not re.match(r"^\s*(?://|#)", l))
    checked = []
    for c in set(PREREG_PATH.findall(code_only)):
        ok, why = sealed(c)
        checked.append((c, ok, why))
        if ok:
            allow(GATE, f"sealed prereg {c}")
    detail = "".join(f"\n     {c} -> {why}" for c, ok, why in checked if not ok)
    block("this looks like an experiment but references no SEALED pre-registration.\n"
          "   Seal one:  python3 gates/prereg_seal.py template payload.json ; edit ; prereg_seal.py new payload.json\n"
          "   Then reference the resulting prereg.json path in the script.\n"
          "   Genuinely not an experiment?  add a line:  // PREREG-EXEMPT: <reason>   (logged)"
          + (f"\n   Candidates found but unsealed:{detail}" if detail else ""), GATE)


if __name__ == "__main__":
    guarded(GATE, main)
