# Prior Art and Positioning

This project does not replace existing audit-trail tools; it composes with them. If your primary need is after-the-fact logging of file reads, tool calls, and command execution across multiple agents, **[Gryph](https://github.com/safedep/gryph)** (Apache-2.0, ~1.5k stars) is the better choice. Gryph integrates natively with Claude Code, Cursor, Gemini CLI, and other agent platforms without wrapper overhead, and its SQLite-backed logging is production-ready. This project and Gryph can run side-by-side; they solve complementary problems.

## Capability Matrix

| Project | Scheduled Heartbeat | Audit Trail | Tamper-Evident (Hash Chain) | Rollback | Pre-Execution Blocking Gate | Incident→Law Pipeline | License |
|---------|:-:|:-:|:-:|:-:|:-:|:-:|---|
| heartbeat-agent-framework | ✅ 30-min tick | Weak (markdown, self-clearing) | ❌ | ❌ | ❌ | ❌ | MIT |
| **Gryph** | ❌ | ✅ Strong (SQLite: files, MCP, commands) | ❌ | ❌ View-only | ❌ Mark, no block | ❌ | Apache 2.0 |
| halo-record | ❌ | ✅ Append-only | ✅ Per-line hash chain | ❌ | ❌ | ❌ | Unspecified |
| CortexIDE | ❌ | ✅ JSONL | Unknown | ✅ File checkpoints | Partial | ❌ | Proprietary |
| AgentBound (paper) | ❌ | ✅ Governance log | Unknown | ❌ | ✅ Pre-mutation gate | ❌ | — |
| Aegis (paper) | ❌ | ✅ Hash-chained | ✅ Verify-or-halt protocol | ❌ | ✅ Gated ops | ❌ | — |
| **This Project** | ✅ Governed period | ✅ Hash-chained ledger | ✅ Chain-verified state | Partial | ✅ Pre-execution gate | ✅ Learned rules | — |

## Academic Grounding

This project implements published frameworks for autonomous-agent governance:

- **AgentBound** ([arXiv 2606.30970](https://arxiv.org/html/2606.30970)) establishes the invariant that every consequential action must pass through an external governance checkpoint before mutating the target system. This project realizes that checkpoint via its pre-execution gate mechanism.

- **Aegis** ([arXiv 2603.16938](https://arxiv.org/html/2603.16938v1)) introduces cryptographic execution-time governance: hash-chained tamper-evident records coupled with verify-or-halt semantics. This project adopts the same ledger approach for its state transitions.

Where this project departs from the literature: it treats the autonomous *period itself* (each scheduled tick) as a governed unit subject to the same chain and gate mechanisms. Literature governance targets discrete *actions*; here, the heartbeat interval is a ledger round with its own integrity proof and decision checkpoint. Additionally, this project implements an incident-to-law-to-gate pipeline absent from published work: each execution failure produces a learned rule that automatically becomes part of the next period's blocking gates, with full lineage from failure case to generated rule to gate application.

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
