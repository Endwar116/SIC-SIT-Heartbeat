# Prior Art and Positioning

This project does not replace existing audit-trail tools; it composes with them. If your primary need is recording every file/tool/command action across many agents — **or policy-based blocking at pre-tool time** — use Gryph; it does both and supports eight agents.

## Capability Matrix

| Project | Scheduled Heartbeat | Audit Trail | Tamper-Evident (Hash Chain) | Rollback | Pre-Execution Blocking Gate | Incident→Law Pipeline | License |
|---------|:-:|:-:|:-:|:-:|:-:|:-:|---|
| heartbeat-agent-framework | ✅ 30-min tick | Weak (markdown, self-clearing) | ❌ | ❌ | ❌ | ❌ | MIT |
| **Gryph** | ❌ | ✅ Strong (SQLite: files, MCP, commands; 8 agents) | ❌ not stated | ❌ View/diff only | ✅ **Yes** — YAML rules block/warn/guide/allow at pre-tool time ("Blocked actions never reach the agent's tool") | ❌ | Apache-2.0 |
| halo-record | ❌ | ✅ Append-only | ✅ Per-line hash chain | ❌ | ❌ | ❌ | Apache-2.0 |
| CortexIDE | ❌ | ✅ JSONL | Unknown | ✅ File checkpoints | Partial | ❌ | Proprietary |
| AgentBound (paper) | ❌ | ✅ Governance log | Unknown | ❌ | ✅ Pre-mutation gate | ❌ | — |
| Aegis (paper) | ❌ | ✅ Hash-chained | ✅ Verify-or-halt protocol | ❌ | ✅ Gated ops | ❌ | — |
| **This Project** | ✅ Governed period | ✅ Hash-chained ledger | ✅ Chain-verified state | Partial | ✅ Pre-execution gate | ✅ Learned rules | — |

## Academic Grounding

This project implements published frameworks for autonomous-agent governance:

- **AgentBound** ([arXiv 2606.30970](https://arxiv.org/html/2606.30970)) establishes the invariant that every consequential action must pass through an external governance checkpoint before mutating the target system. This project realizes that checkpoint via its pre-execution gate mechanism.

- **Aegis** ([arXiv 2603.16938](https://arxiv.org/html/2603.16938v1)) introduces cryptographic execution-time governance: hash-chained tamper-evident records coupled with verify-or-halt semantics. This project adopts the same ledger approach for its state transitions.

Where this project departs from the literature: it treats the autonomous *period itself* (each scheduled tick) as a governed unit subject to the same chain and gate mechanisms. Literature governance targets discrete *actions*; here, the heartbeat interval is a ledger round with its own integrity proof and decision checkpoint. Additionally, this project implements an incident-to-law-to-gate pipeline absent from published work: each execution failure produces a learned rule that is written down with its lineage and, once someone writes the gate, enforced — the pipeline is manual by design, with full lineage from failure case to generated rule to gate application.

## Non-Goals

- **Not an observability platform.** We do not replace dashboards, metrics systems, or distributed tracing. This project's logs are for auditability and governance, not performance insights.
- **Not a git replacement.** We do not manage source code history or provide merge/rebase semantics. We record execution state and decisions, not code evolution.
- **Not a sandbox.** We provide no execution isolation. If the host is compromised, audit logs are compromised.
- **Not a guarantee against host compromise.** Hash chains and verification gates defend against *accidental* mutation or post-hoc tampering by the system itself; they cannot defend against an adversary with kernel-level access. Assume an honest but fallible automation layer.

## References

- [heartbeat-agent-framework](https://github.com/muxueqingze/heartbeat-agent-framework) — MIT-licensed heartbeat scheduler framework
- [Gryph](https://github.com/safedep/gryph) — Production audit trail for multi-agent platforms (Apache 2.0)
- [halo-record](https://github.com/bkuan001/halo-record) — Append-only event log with per-record hash chaining
- [Behavioral Governance for Autonomous AI Agents: The AgentBound Framework](https://arxiv.org/html/2606.30970) — External governance checkpoint invariant
- [Cryptographic Runtime Governance for Autonomous AI Systems: The Aegis Architecture for Verifiable Policy Enforcement](https://arxiv.org/html/2603.16938v1) — Hash-chained tamper-evident logging with verify-or-halt
- [IMDA Agentic AI Governance Framework](https://www.imda.gov.sg) — National governance requirements for autonomous agents (Singapore, 2026-01)
- [DEMM-Bench: A Benchmark for Evidence-Sufficient Governance of Autonomous Agents](https://arxiv.org/pdf/2606.20634) — Evaluation framework for execution-time governance mechanisms

## Correction (2026-09-04)

An earlier version of this page said Gryph only "marks, does not block" and quoted "~1.5k stars", both taken from a
third-party blog post. Reading Gryph's own README: it **does** block at pre-tool time via YAML rules, and showed 161 stars.
Corrected here per our own law-003 (numbers are measured at the source). What this repository adds over Gryph is
therefore narrower and more precise: a hash-chained per-tick ledger, reversible deletes with tombstones, the governed
heartbeat itself, and the incident→law→gate pipeline.
