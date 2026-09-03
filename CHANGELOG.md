# Changelog

## 0.2.0 — 2026-09-04 — after adversarial review

An independent reviewer cloned `v0.1.0` and ran 82 crafted commands through the deletion gate and 8 failure
scenarios through the ledger. Verdict: "not credible as a reference implementation today". They were right.
Everything below is a response to a demonstrated defect, not a feature.

**Gate (`gates/file_governance.py`) — rebuilt.** v1 was a substring regex and passed 49/70 destructive forms
(`\rm`, quoted/escaped names, `/bin/rm`, `RM`, `bash -c`, `$(…)`, `xargs rm`, destructive git, truncations,
interpreter one-liners, `rsync --delete`) while whitelisting the trash directory and any path under `/tmp/../`.
v2 normalises quotes, matches at command position, covers those classes, confines "safe" deletes with
realpath+commonpath, removes the trash from the allow-list, hooks `Write`/`Edit` for truncation, and *warns*
(allows + logs) on high-false-positive shapes (`tee`, `sed -i`, pipe into shell, `eval`) — stated as residual risk.
Test: a table-driven battery of 57 must-block / 17 must-allow / 5 must-warn cases.

**Ledger (`ledger/ledger.py`) — format 2.** v1 hashed only `prev_hash + state`, so `seq` and `logged_at` were
forgeable; had no lock (8 concurrent appends corrupted the chain); enforced no round/identity continuity; a torn
final line bricked the ledger; `STATE_CURRENT.json` could silently desync. v2 hashes the whole wrapper, holds
`flock` across the append, enforces `round == prev+1` and constant `entity.name` (overridable with a recorded
reason), detects torn tails and ships `repair --torn-tail`, cross-checks `STATE_CURRENT.json` in `verify`,
rejects non-finite floats and non-object blocks (exit 2, no tracebacks), NFC-normalises strings, fsyncs the
directory. Format-1 chains still verify.

**Rollback (`rollback/tombstone.py`).** `restore` used to parse markdown, so a crafted `--why` could redirect it;
symlinks were resolved and their targets trashed; same-second name collisions; manifest never re-checked. Now:
`tombstone.json` is the only source of truth, `--why` is one line, symlinks are refused, entry names carry
microseconds, the manifest is recomputed after the move and before any restore.

**Gates (others).** `_hook.py`: every gate is wrapped so an exception *allows and records* instead of crash-
exiting 1; malformed payloads are handled; every verdict (allow/warn/block/error) is logged.
`prereg_gate.py`: sidecar digests are compared, `FROZEN` must be a `status:` line, paths in comments do not
count, the trigger is word-bounded and requires a script reference (no more blocking `git commit -m "retrieve…"`).
`monitor_dedup.py`: word-bounded topic, token-set comparison, and `register|stop` subcommands; `run_loop.sh`
registers itself and unregisters on exit, so the gate can actually fire out of the box.
`decision_card.py`: `ISO-`/`RFC-`/`SHA-`… are not "unexplained codenames".

**Heartbeat.** `health.py`: `-9` is a normal exit, default scope is jobs with a plist in `~/Library/LaunchAgents`
(a stock Mac no longer shows 141 "problems"), Linux counts only `failed` units, and a **missing hook target**
(exit 127 = gate silently off) is reported. `tick.sh` records `laws_debts:N`. `run_loop.sh` uses `mktemp`.
CI asserts the tick's exit code instead of `|| true`.

**Docs made to match code.** Gryph *does* block at pre-tool time and showed 161 stars (we had repeated a blog's
"marks only" / "1.5k"); README and PRIOR_ART corrected and a correction note kept. "Automatically becomes a gate"
→ "manually". law-005 is `none-yet`; law-007 is a `checker`. SPEC_LEDGER rewritten for format 2. INTEROP.md,
SECURITY.md, acknowledgements, `install.sh --check/--uninstall`, workflow badge. Timestamps in laws are UTC.

Tests: 45+. Still standard library only.

## Unreleased

* **gates/decision_card.py** — salience checks E1–E3 (bold one-glance line, bold option words, recommendation
  bolds one option); `laws/examples/law-010.json` (refines law-006). Regex bug fixed: recommendation line is
  matched from line start, not from the keyword.
* **gates/monitor_dedup.py** — loop-fingerprint matching (registries hold summaries, not exact commands).
* **docs/INTEROP.md**, **SECURITY.md**, README "Works alongside" + "Acknowledgements".
* 21 tests.

## 0.1.0 — 2026-09-03

First public release. Everything here was in daily use by the maintainers before it was published.

* **ledger/** — append-only hash-chained SIC-JS 4.0 rounds; `verify`; atomic current state;
  `AI_SELF_CLOSED` governance flag; `derive.py` (truth-source derivation); `anchor.py`
  (canonical transcript↔ledger anchor, drift check/fix, coverage).
* **gates/** — `file_governance` (no hard delete), `monitor_dedup` (no duplicate watchers),
  `prereg_gate` + `prereg_seal` (no experiment without a sealed pre-registration),
  `decision_card` (five elements, ≤3 open). Every decision logged.
* **rollback/** — `tombstone.py`: trash + tombstone + sha256 manifest + restore; humans empty the trash.
* **heartbeat/** — `tick.sh` (one governed tick), `run_loop.sh`, `health.py` (quiet-death detector,
  three signals + external-volume-log configuration), `zombie.py` (TTL on pending items, receipts to close).
* **laws/** — schema, `legislate.py`, nine de-identified laws from real incidents (law-009 is an
  honest `none-yet` debt).
* **install/** — `install.sh` (Claude Code hooks, backs up settings), INSTALL.md for three
  environments, launchd template with the internal-disk-log lesson baked in.
* 20 tests, standard library only, CI on ubuntu + macos × Python 3.9/3.11/3.12.
