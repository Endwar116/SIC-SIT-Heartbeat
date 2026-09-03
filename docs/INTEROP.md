# Works alongside — how this composes with existing tools

This project is deliberately narrow: it governs the **tick** and gates **mutation**. Several excellent
tools cover neighbouring ground better than we do. Use them together. None of the integrations below
have been tested end-to-end by us yet — this page says how the pieces *fit*, and we would welcome a
PR that proves one.

| you want | use | how it fits with this repo |
|---|---|---|
| Every file read/write, MCP call and command your agent makes, across Claude Code / Cursor / Gemini CLI / Windsurf / OpenCode / Pi, in a queryable local DB | **[Gryph](https://github.com/safedep/gryph)** (Apache-2.0, SafeDep) | Gryph is the **recorder**; we are the **gate + ledger**. Run both. Gryph tells you *everything that happened*; our ledger tells you *what each tick claimed and whether history was altered*; our gates stop the destructive subset before it happens. A future `tick.sh` step could cross-check the Gryph session diff against the round's `current_action`. |
| A hash-chained, append-only record of tool/model calls as a Python library, with secret/PII redaction | **[halo-record](https://github.com/bkuan001/halo-record)** | Same integrity idea as `ledger/ledger.py`, at a different grain (per call, not per tick). Their redaction-before-write is something our ledger does not do — a `ledger.py` pre-write redaction hook would be a natural port. |
| A 30-minute heartbeat that picks the highest-priority project from a markdown file and makes progress | **[heartbeat-agent-framework](https://github.com/muxueqingze/heartbeat-agent-framework)** (MIT) | Their `PROJECTS.md` pattern is a good **work source** for the "(work)" step in our loop. Our contribution is what wraps it: identity gate before, hash-chained round after, non-zero exit on red. |
| Per-step file checkpoints and one-click rollback inside an IDE | **CortexIDE** (commercial) | IDE-level undo. Our `rollback/tombstone.py` works at the filesystem level and survives outside any editor; the two are complementary. |
| The theory | **[AgentBound](https://arxiv.org/html/2606.30970)** (external governance checkpoint before target-system mutation) · **[Aegis](https://arxiv.org/html/2603.16938v1)** (hash-chained tamper-evident logging, verify-or-halt) · **[DEMM-Bench](https://arxiv.org/pdf/2606.20634)** (governance-evidence sufficiency benchmark) | We are an installable reference implementation of the first two ideas. DEMM-Bench is the natural yardstick if anyone wants to evaluate this repo formally. |

## Composing with Gryph — sketch

```
Claude Code ──PreToolUse──▶ our gates (block / allow, logged)
             ──native hooks─▶ Gryph (records what actually ran)
scheduler ───▶ tick.sh ───▶ our ledger round (hash-chained, exit 0/1)
                             └─ optional: `gryph diff --session <id>` pasted into the round's evidence
```

## What we do not do, on purpose

* We do not record every action — Gryph does.
* We do not sandbox — a compromised host defeats every gate here (see [THREAT_MODEL.md](THREAT_MODEL.md)).
* We do not replace git — the tombstone is for things git does not track.

If you maintain one of the projects above and we have described it wrongly, open an issue; we will fix the description, not defend it.
