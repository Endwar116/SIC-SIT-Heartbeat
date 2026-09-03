#!/usr/bin/env python3
"""file_governance.py — the deletion gate (PreToolUse: Bash, Write, Edit).

Rule (docs/SPEC_GATES.md): delete = move to TRASH + tombstone. Never hard-delete, never truncate.

v2 (after adversarial review): the first version was a substring regex on the raw string and passed
49 of 70 destructive forms (`\\rm`, `'rm'`, `/bin/rm`, `RM`, `bash -c "rm"`, `$(rm)`, `xargs rm`,
`git reset --hard`, `: > f`, `truncate -s0`, interpreter deleters…) while blocking prose that merely
mentioned rm. It also whitelisted the trash itself. This version:
  * normalises quotes/backslashes first (bash concatenates 'r''m' into rm)
  * matches deleters at COMMAND position (start, after ; & | ( { ` $( ), case-insensitively, with or
    without a path prefix
  * covers find -delete, destructive git, truncation forms, interpreter deleters, rsync --delete
  * confines "safe" deletes with realpath + commonpath (no `/tmp/../`, no `/tmpfoo`, no `~`), and the
    trash is NOT safe — only rollback/tombstone.py touches it
  * warns (allows + logs) on high-false-positive shapes: tee, sed -i, piping into a shell, eval
  * hooks Write/Edit: writing empty content over a non-empty file is a truncation
Residual risk, stated: `x=rm; $x`, `printf … | sh`, `base64 -d | sh` are only warned, never blocked.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook import read_payload, block, warn, allow, guarded  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ledger"))
import paths  # noqa: E402

GATE = "file-governance"
# command position = start of line, after a separator, or after a prefix command that executes its argument.
# NOT after arbitrary whitespace — that made `echo do not run rm here` a "delete".
CMD_START = r"(?:^\s*|[;&|(){}`]\s*|\$\(\s*)"
PREFIX = r"(?:(?:sudo|doas|exec|command|builtin|env|nohup|nice|time|xargs|(?:ba|z|da)?sh\s+-c)\s+(?:-\S+\s+)*)?"
RM = re.compile(CMD_START + PREFIX + r"(?:/[\w./-]*/)?(?:rm|rmdir|shred|unlink|srm|wipe)(?=\s|$|[;&|)])", re.I)
RM_ALLOW = re.compile(r"\b(?:docker|podman|cargo|brew|helm|kubectl|npm|yarn|pnpm|pip[0-9]*|gem|apt(?:-get)?)\s+rm\b|\bgit\s+rm\b.*--cached", re.I)
FIND_DELETE = re.compile(r"\bfind\s.*\s-delete(?=\s|;|\)|$)")
GIT = re.compile(r"\bgit\s+(?:clean\b(?=.*(?:\s-[a-zA-Z]*f[a-zA-Z]*\b|\s--force\b))|checkout\s+(?:--|\.)(?=\s|$)|restore\b(?!\s+--staged)|reset\s+--hard\b|stash\s+(?:drop|clear)\b|branch\s+-D\b|push\b.*(?:\s-f\b|--force\b(?!-with-lease))|rm\b(?!.*--cached))")
TRUNC = re.compile(r"(?:^|[;&|]\s*)(?::|true|echo(?:\s+-n)?|cat\s+/dev/null|printf)?\s*>\|?\s*(?!>|&)\S+")
TRUNC2 = re.compile(r"\btruncate\s+(?:-s\s*0|--size[= ]0)\b|\bdd\b[^|]*\bof=(?!/dev/)|\bcp\s+/dev/null\s+\S")
INTERP = re.compile(r"\b(?:python[0-9.]*|perl|ruby|node|php)\s+-[cer]\b[^|]*\b(?:rmtree|os\.(?:remove|unlink|rmdir)|unlink|File\.delete|rm(?:Sync)?\(|unlinkSync|open\([^)]*[,\s]w)")
RSYNC = re.compile(r"\brsync\b.*--delete")
WARN_ONLY = re.compile(r"\btee\s+(?!-a\b)(?!/dev/)\S+|\bsed\s+-i\b|\|\s*(?:ba|z|da)?sh\b|\beval\b|\bbase64\s+-d\b.*\|")
SAFE = [os.path.realpath(p) for p in dict.fromkeys([os.environ.get("TMPDIR", ""), "/tmp", "/private/tmp"]) if p and len(p) > 3]


def normalise(cmd: str) -> str:
    return re.sub(r"""["'\\]""", "", cmd)


TRASH_RP = os.path.realpath(str(paths.TRASH))


def confined_to_temp(cmd: str) -> bool:
    """Every path token resolves under a temp root — and none of them is the trash (the trash is never
    'safe', even when HEARTBEAT_HOME itself lives under the temp directory)."""
    toks = re.findall(r"(?:~|\$HOME|/)\S*", cmd)
    if not toks:
        return False
    for t in toks:
        if t.startswith(("~", "$HOME")):
            return False
        rp = os.path.realpath(os.path.normpath(t.rstrip(";&|)")))
        if os.path.commonpath([rp, TRASH_RP]) == TRASH_RP:
            return False
        if not any(os.path.commonpath([rp, sp]) == sp for sp in SAFE):
            return False
    return True


def check_bash(cmd: str):
    c = normalise(cmd)
    hit = None
    if RM.search(c) and not RM_ALLOW.search(c):
        hit = "hard delete (rm/rmdir/shred/unlink)"
    elif FIND_DELETE.search(c):
        hit = "find -delete"
    elif GIT.search(c):
        hit = "destructive git (clean -f / checkout -- / restore / reset --hard / stash drop / branch -D / push --force / rm)"
    elif TRUNC.search(c) or TRUNC2.search(c):
        hit = "file truncation"
    elif INTERP.search(c):
        hit = "interpreter one-liner that deletes or truncates"
    elif RSYNC.search(c):
        hit = "rsync --delete"
    if hit:
        if confined_to_temp(c):
            allow(GATE, f"{hit} confined to temp")
        block(f"{hit} detected.\n"
              f"   Rule: delete = move into {paths.TRASH} + TOMBSTONE (reversible 30 days). Never hard-delete or truncate.\n"
              f"   Do it with:  python3 rollback/tombstone.py trash <path> --why \"<one-line reason>\"\n"
              f"   Command was: {cmd[:160]}", GATE)
    if WARN_ONLY.search(c):
        warn(f"pattern with destructive potential allowed (tee / sed -i / pipe into shell / eval): {cmd[:100]}", GATE)
    allow(GATE)


def check_write(tool: str, ti: dict):
    path = ti.get("file_path") or ti.get("path") or ""
    if not path:
        allow(GATE)
    p = Path(str(path)).expanduser()
    if tool == "Write" and ti.get("content", None) == "" and p.exists() and p.stat().st_size > 0:
        block(f"Write with empty content over non-empty {p} is a truncation. Trash it instead:\n"
              f"   python3 rollback/tombstone.py trash \"{p}\" --why \"<reason>\"", GATE)
    if tool == "Edit" and ti.get("new_string", None) == "" and p.exists():
        try:
            if ti.get("old_string", "\x00") == p.read_text(encoding="utf-8", errors="ignore"):
                block(f"Edit that replaces the entire content of {p} with nothing is a truncation.", GATE)
        except OSError:
            pass
    allow(GATE)


def main():
    p, problem = read_payload()
    if problem:
        allow(GATE, f"unparseable payload allowed: {problem}")
    tool = p["tool_name"]; ti = p["tool_input"]
    if tool == "Bash":
        cmd = ti.get("command", "")
        if not isinstance(cmd, str):
            allow(GATE, "command is not a string; allowed")
        check_bash(cmd)
    if tool in ("Write", "Edit", "NotebookEdit"):
        check_write(tool, ti)
    allow()


if __name__ == "__main__":
    guarded(GATE, main)
