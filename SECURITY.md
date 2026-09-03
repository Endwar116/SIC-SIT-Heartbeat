# Security

## Reporting

Open a GitHub issue titled `security:` for anything that is not an active exploit. For something you
believe should not be public yet, open a minimal issue saying only "private security report" and a
maintainer will move the conversation to a private channel.

## What counts

* A **gate bypass**: a command that destroys data yet passes `gates/file_governance.py`, or a watcher
  that duplicates yet passes `gates/monitor_dedup.py`. Please include the exact command/JSON.
* A **ledger integrity gap**: a way to alter a past round that `ledger.py verify` does not detect,
  beyond the documented limitation (deleted trailing lines).
* A **tombstone gap**: a delete path that leaves no restorable copy.
* **Re-identification**: anything in this repository or its history that identifies a real person,
  organisation, or machine. We will rewrite history if needed (see `laws/examples/law-004.json`).

## What does not count

* Disabling the hooks in `settings.json` — the threat model assumes the operator controls the harness.
* Anything that requires root or write access to the ledger directory — the chain is tamper-evident,
  not tamper-proof (see `docs/THREAT_MODEL.md`).

## Supported versions

Only the latest tagged release.
