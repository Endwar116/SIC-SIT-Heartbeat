#!/usr/bin/env python3
"""release_check.py — the pre-release gate (law-011: verify the shipped artifact, not the source tree).

What it does, in order, and stops at the first failure (exit 1):
  1. clones the current HEAD into a temp dir and runs the test suite there — a clean checkout, not your tree
  2. scans every file in that clone for strings that must never ship (internal paths, private ids, tokens)
  3. checks that the test count written in README/CHANGELOG matches the count the suite actually reports
Run it before tagging a release:  python3 scripts/release_check.py
CI runs it on every push (see .github/workflows/ci.yml).
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A real machine path is a mount/user name followed by a deeper segment; the bare prefixes "/Volumes/,"
# and "/Users/<placeholder>" that the docs and tests use as examples are allowed.
NEVER_SHIP = [
    r"/Volumes/[A-Za-z0-9_-]+/[^\s'\"]", r"/Users/[a-z][a-z0-9_-]{2,}/[^\s'\"]", r"\.vsde", r"\.wxjde", r"AGENT_EXCHANGE",
    r"三樓", r"四樓", r"\bU[0-9a-f]{32}\b", r"\bC[0-9a-f]{32}\b", r"nvapi-", r"LINE_CHANNEL", r"sk-[A-Za-z0-9]{20,}",
]
SKIP_DIRS = {".git", "__pycache__"}


def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main():
    tmp = tempfile.mkdtemp(prefix="release-check-")
    r = sh(["git", "clone", "-q", ROOT, tmp], cwd=ROOT)
    if r.returncode:
        print("❌ clone failed:", r.stderr.strip()[:200]); return 1
    # 1. tests in the clean clone
    t = sh([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=tmp)
    m = re.search(r"Ran (\d+) tests", t.stderr)
    if t.returncode or not m:
        print("❌ tests failed in a clean clone:\n" + t.stderr[-600:]); return 1
    ran = int(m.group(1))
    print(f"✅ clean clone: {ran} tests OK")
    # 2. never-ship scan
    hits = []
    for base, dirs, files in os.walk(tmp):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = os.path.join(base, f)
            try:
                txt = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if f == "release_check.py":
                continue  # this file lists the patterns themselves
            for pat in NEVER_SHIP:
                for mm in re.finditer(pat, txt):
                    line = txt.count("\n", 0, mm.start()) + 1
                    hits.append(f"{os.path.relpath(p, tmp)}:{line}: {pat}")
    if hits:
        print("❌ strings that must never ship:\n  " + "\n  ".join(hits[:20])); return 1
    print("✅ never-ship scan: 0 hits")
    # 3. documented counts match measured
    bad = []
    for doc in ("README.md", "CHANGELOG.md"):
        txt = open(os.path.join(tmp, doc), encoding="utf-8").read()
        for n in set(re.findall(r"Ran (\d+) tests", txt)):
            if int(n) != ran:
                bad.append(f"{doc} says 'Ran {n} tests', suite ran {ran}")
    if bad:
        print("❌ " + "; ".join(bad)); return 1
    print("✅ documented test count matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
