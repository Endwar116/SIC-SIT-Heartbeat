# Changelog

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
* 19 tests, standard library only, CI on ubuntu + macos × Python 3.9/3.11/3.12.
