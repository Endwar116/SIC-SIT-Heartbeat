#!/usr/bin/env python3
"""file_governance.py — the deletion gate (PreToolUse: Bash).

Rule (docs/SPEC_GATES.md, axioms AX2/AX5/AX6):
  Delete = move to TRASH + write a tombstone. Never `rm`. Never `shred`. Never `> file` to empty it.
  Every destructive operation must be reversible for 30 days and traceable by grep.

Blocks:  rm / rm -r / rm -rf / rmdir / shred / unlink / find ... -delete / git clean -f / truncation
Allows:  everything else, and rm inside $TMPDIR or the trash dir itself (already governed)

Why a gate and not a guideline: the agent that wrote this gate was blocked by it twice on the
same day while trying to "just clean up a test directory". Guidelines do not fire at 3 a.m.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook import read_payload, block, allow  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

GATE = "file-governance"
DESTRUCTIVE = [
    (r"(^|[;&|]\s*|\s)rm\s", "rm"),
    (r"(^|[;&|]\s*|\s)rmdir\s", "rmdir"),
    (r"(^|[;&|]\s*|\s)shred\s", "shred"),
    (r"(^|[;&|]\s*|\s)unlink\s", "unlink"),
    (r"find\s.*\s-delete(\s|$)", "find -delete"),
    (r"git\s+clean\s+-[a-zA-Z]*f", "git clean -f"),
    (r"(^|[;&|]\s*)\s*>\s*[^>]\S+\s*$", "truncate-by-redirect"),
]
SAFE_PREFIXES = [os.environ.get("TMPDIR", "/tmp"), "/tmp", "/private/tmp", str(paths.TRASH)]


def main():
    p = read_payload()
    if not p or p.get("tool_name") != "Bash":
        allow()
    cmd = (p.get("tool_input") or {}).get("command", "") or ""
    for pat, name in DESTRUCTIVE:
        if re.search(pat, cmd):
            # tolerate deletes that stay inside temp or the trash itself
            targets = re.findall(r"(/\S+)", cmd)
            if targets and all(any(t.startswith(sp) for sp in SAFE_PREFIXES) for t in targets):
                allow(GATE, f"{name} confined to temp/trash")
            block(
                f"hard delete detected ({name}).\n"
                f"   Rule: delete = move into {paths.TRASH} + write TOMBSTONE.md (reversible 30 days).\n"
                f"   Do it with:  python3 rollback/tombstone.py trash <path> --why \"<one-line reason>\"\n"
                f"   Command was: {cmd[:160]}",
                GATE)
    allow()


if __name__ == "__main__":
    main()
