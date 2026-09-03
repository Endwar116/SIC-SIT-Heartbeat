# SIC-SIT-Heartbeat

**Leave an agent running overnight. Come back. Audit every tick, roll back any deletion, and see exactly which file and which rule need to change.**

[![CI](https://img.shields.io/badge/tests-19%20passing-brightgreen)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B%20stdlib%20only-informational)

Works with **Claude Code** (CLI, VS Code extension, desktop app) via `PreToolUse` hooks, and with any
**terminal scheduler** (cron / launchd / systemd) via one script. No dependencies beyond the Python
standard library. English docs; [繁體中文](README.zh-TW.md).

---

## The problem

An autonomous agent on a heartbeat wakes up at 3 a.m. and acts. Nobody is watching. Existing tools
record what it did (well — see [Prior art](docs/PRIOR_ART.md)). Almost none of them:

* stop a destructive command **before** it runs,
* make the record **tamper-evident**, so the agent cannot quietly fix its own history,
* make deletion **reversible** by default,
* treat the **tick itself** as the unit of governance, or
* turn the incident that happened last night into a **rule that fires** tomorrow.

This repository does those five things, as small standard-library Python you can read in an afternoon.

## What you get after a night of unattended ticks

| question | answer lives in | command |
|---|---|---|
| What happened, round by round? | `ledger/events.log` | `cat` |
| Did anyone — including the agent — alter history? | hash chain over every round | `python3 ledger/ledger.py verify` |
| What did the gates block, when, why? | `state/gate_decisions.jsonl` | `cat` |
| What was deleted, and how do I put it back? | `trash/*/TOMBSTONE.md` | `python3 rollback/tombstone.py restore <entry>` |
| Which services died quietly? | machine check, three signals | `python3 heartbeat/health.py` |
| What went wrong before, and does anything enforce the lesson yet? | `laws/` | `python3 laws/legislate.py debts` |

## The loop

```
scheduler ─▶ wake-up gate ─▶ checks ─▶ (work, gates fire before mutation) ─▶ ledger round ─▶ exit 0/1
                                                                                  │
                                                       incident? ──▶ law ──▶ gate (or a recorded debt)
```

Every tick appends one **SIC-JS 4.0** round to an append-only ledger where
`hash = sha256(prev_hash + canonical(state))`. Fields that can drift (round number, upstream hash,
identity, timestamp) are derived by code from the ledger itself; only the semantic fields come from the
agent. The agent may claim its task is *completed*; the ledger records the claim and raises a permanent
`AI_SELF_CLOSED` flag — completion is the operator's stamp, not the agent's word.

Full description: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
[Ledger spec](docs/SPEC_LEDGER.md) · [Gates](docs/SPEC_GATES.md) ·
[Incident → law](docs/SPEC_INCIDENT_LAW.md) · [Threat model](docs/THREAT_MODEL.md)

## Quickstart

```bash
git clone https://github.com/Endwar116/SIC-SIT-Heartbeat && cd SIC-SIT-Heartbeat
./install/install.sh                 # Claude Code: backs up ~/.claude/settings.json, adds 3 hooks
python3 ledger/ledger.py verify      # ✅ chain intact — 0 rounds
./heartbeat/tick.sh                  # one governed tick → prints  ⚓ R1 · seq1 · <hash16>
python3 -m unittest discover -s tests
```

Then try to delete something from inside Claude Code:

```
> rm -rf ./scratch
⛔ file-governance: hard delete detected (rm).
   Rule: delete = move into ~/.sic-sit-heartbeat/trash + write TOMBSTONE.md (reversible 30 days).
   Do it with:  python3 rollback/tombstone.py trash ./scratch --why "<one-line reason>"
```

Terminal-only and VS Code notes: [install/INSTALL.md](install/INSTALL.md).

## The gates (run *before* the tool)

| gate | blocks | born from |
|---|---|---|
| `gates/file_governance.py` | `rm`, `shred`, `find -delete`, `git clean -f`, truncation — outside temp/trash | the maintainers' own hard-delete attempts |
| `gates/monitor_dedup.py` | mounting a watcher equivalent to one already registered active | three heartbeats firing after an *assumed* clock death |
| `gates/prereg_gate.py` | any experiment that references no **sealed** pre-registration | three benchmark rounds run with the template unused |
| `gates/decision_card.py` | a human-escalated decision missing any of five elements; >3 open at once | an operator facing 21 unanswerable cards |

Contract: JSON on stdin, **exit 2 blocks** (reason to the agent), exit 0 allows, a crashing gate allows
and logs. Every decision is appended to `state/gate_decisions.jsonl`. Details: [docs/SPEC_GATES.md](docs/SPEC_GATES.md).

## The laws

`laws/examples/` holds nine incidents from real operation, de-identified, each turned into a rule with
checkable conditions and a named enforcer (or an honest `none-yet`). Two to read first:

* **law-007** — peripheral signals (exit codes, missing logs, process lists) *open* an investigation;
  only the subject's own record can *close* it. Rule out "finished on purpose" before "died".
* **law-008** — before deciding something under delegated authority, look for a rule already bound to
  it (code, standing orders, design-time approval conditions). Intuition was wrong 3 of 3 times.

The pipeline is a tool, not a document: `python3 laws/legislate.py new --what ... --text ... --check ... --enforce gate --ref gates/x.py`.

## Prior art, honestly

If you only need after-the-fact logging of file/tool/command activity across many agents, use
[Gryph](https://github.com/safedep/gryph) — it does that better than this repository will.
The architecture here is a reference implementation of two published designs — an external
governance checkpoint before target-system mutation ([AgentBound](https://arxiv.org/html/2606.30970))
and hash-chained tamper-evident logging with verify-or-halt ([Aegis](https://arxiv.org/html/2603.16938v1))
— plus two things the literature does not cover: governing the autonomous *period itself*, and the
incident → law → gate pipeline. Full matrix: [docs/PRIOR_ART.md](docs/PRIOR_ART.md).

## Status

`v0.1.0`. Used in daily operation by the maintainers on macOS; Linux paths are best-effort;
Windows is not supported. Standard library only; tests run on 3.9–3.12. The hash chain is
tamper-**evident**, not tamper-proof — read the [threat model](docs/THREAT_MODEL.md) before relying on it.

## License

MIT — see [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
