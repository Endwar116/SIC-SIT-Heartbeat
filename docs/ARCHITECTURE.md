# Architecture — the governed loop

This project treats an autonomous agent's *heartbeat* — the moment it wakes on a schedule and
acts without a human present — as the unit of governance. Not the action. The tick.

```
            ┌──────────────────────────────────────────────────────────────┐
            │                        one tick                              │
            │                                                              │
 scheduler ─┼─▶ wake-up gate ─▶ checks ─▶ (work) ─▶ ledger round ─▶ exit  │
 (cron /    │   identity      services    gates      hash-chained   0 / 1  │
  launchd / │   lineage       zombies     fire       anchor         RED    │
  Monitor)  │   chain         inbox       before     printed               │
            │                 chain       mutation                          │
            └──────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                     incident? ──▶ law ──▶ gate (or a recorded debt)
```

## The five parts

| part | directory | what it guarantees |
|---|---|---|
| **Ledger** | `ledger/` | Every round is one appended line; `hash = sha256(canonical(whole line minus hash))` — seq, timestamp and state are all covered. Editing any past round breaks every later hash. `verify` recomputes the whole chain. Current state is replaced atomically. |
| **Gates** | `gates/` | Run *before* a tool executes (Claude Code `PreToolUse`; adaptable). Exit 2 blocks and the reason reaches the agent. Every gate decision is itself appended to `state/gate_decisions.jsonl`. |
| **Rollback** | `rollback/` | Delete = move into trash + tombstone (who/when/why/how-to-undo) + sha256 manifest. Restore is one command. Only a human empties the trash. |
| **Heartbeat** | `heartbeat/` | `tick.sh` runs machine-judged checks (chain integrity, quiet-death of services, zombie items, inbox), records one round carrying the results, exits non-zero if anything is red. It never invents work. |
| **Laws** | `laws/` | `incident → law → gate`. A law without an enforcing gate is a *recorded debt*, listed by `legislate.py debts`. Laws from different incidents are parallel, not versions of each other. |

## Wake-up (law-002)

Step zero of every tick, before any work:

1. **identity** — `entity.name` of the round about to be written equals the installation's configured agent (`HEARTBEAT_AGENT`), not something inferred from the working directory.
2. **round continuity** — `round == previous.round + 1`.
3. **chain lineage** — `prev_hash` equals the stored hash of the previous round.
4. **corrupted variants** — the last N rounds parse and validate.
5. **positional drift** — no round in the last N carries a different `entity.name`.

`ledger.py append` refuses a round that fails 1–3 (unless a `--allow-discontinuity` reason is recorded);
`ledger.py verify` re-checks 2–5 over the whole chain and cross-checks `STATE_CURRENT.json`.

## Truth sources, not memory

Fields that can drift are derived by code from a source of truth; only semantic fields are supplied by the agent:

| field | source |
|---|---|
| `round` | last round in the ledger + 1 |
| `relation.upstream` | recomputed hash of the previous round |
| `entity.name` / `entity.model` | installation config / harness environment — a model cannot attest its own identity |
| `event.timestamp` | system clock |
| `task.*` | inherited from the previous round (inheritance is copying, not remembering) |
| `state.context`, `current_action`, `intent.*` | the agent — code cannot derive meaning and does not pretend to |

## Completion is a stamp, not a claim

The agent may write `task.status = completed`; the ledger records it and raises `governance_flag: AI_SELF_CLOSED`.
Nothing is blocked — the ledger records, gates enforce — but the flag is loud and permanent. In practice the
operator (or a designated verifier) is the only party who closes work. This single rule is the spine of the
whole system: most of the incidents in `laws/examples/` are variations of an agent believing its own "done".

## What a reader gets

After a night of unattended ticks:

* `ledger/events.log` — one line per round: time, round, hash prefix, what happened.
* `ledger.py verify` — did anyone (including the agent) alter history? Yes/no, and where.
* `state/gate_decisions.jsonl` — what the gates blocked, when, why.
* `trash/*/TOMBSTONE.md` — what was removed and how to put it back.
* `laws/` — what went wrong before, what rule came out of it, whether anything enforces it yet.

That is the whole promise: **you can leave, come back, audit, roll back, and see exactly which file and which
rule need to change.**
