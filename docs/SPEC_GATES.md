# Gates — preventive control before mutation

A gate is a small program that runs *before* a tool call and decides. It is not advice.
The agent that wrote these gates was blocked by its own deletion gate twice in one afternoon
while trying to "just clean up a test directory". That is the point.

## Contract

| | |
|---|---|
| input | JSON on stdin: `{"tool_name": "...", "tool_input": {...}}` (Claude Code `PreToolUse` shape) |
| allow | exit **0** |
| block | exit **2** — stderr is delivered to the agent as the reason |
| never | exit 1 for policy: it only warns and the action still runs |
| budget | < 500 ms; a gate that crashes must *allow* and log the anomaly, never crash-block |
| evidence | every decision appended to `state/gate_decisions.jsonl` |

## The six axioms behind the deletion gate

Adapted from a file-governance rulebook used in production by the maintainers; kept here as the
rationale, not as scripture.

| axiom | meaning | how it shows up here |
|---|---|---|
| **AX1 files are semantic objects** | "organised" is not "done"; every move carries a stated intent | tombstone requires `--why` |
| **AX2 destructive ops are logged, append-only** | confirm the log is writable → act → log success *and* failure | `gate_decisions.jsonl`, `TOMBSTONE.md` |
| **AX3 rules over judgement** | a written rule beats an efficient shortcut; no rule → stop and ask | gates fire regardless of how reasonable the command looks |
| **AX4 dry run by default** | batch operations are previewed and confirmed by a human, never self-confirmed | out of scope for this repo; see notes |
| **AX5 traceable, explainable, reversible** | `grep <path>` finds the full history; delete = trash; humans empty trash | `rollback/tombstone.py` |
| **AX6 copy first, never delete source** | move = copy, verify sha256, then remove | tombstone writes a sha256 manifest before moving |

## Residual risk, stated

`x=rm; $x`, `printf … | sh`, `base64 -d | sh`, `eval` cannot be caught by pattern matching without blocking
half of ordinary shell use; they are **warned** (allowed, logged), not blocked. A sandbox, not a gate, is the
answer to a determined agent. See THREAT_MODEL.

## Shipped gates

| gate | hook target | blocks | incident |
|---|---|---|---|
| `file_governance.py` | `Bash`, `Write`, `Edit` | `rm`, `rmdir`, `shred`, `unlink`, `find -delete`, `git clean -f`, truncation by redirect (outside temp/trash) | the maintainers' own repeated attempts to hard-delete |
| `monitor_dedup.py` | `Monitor` (or any watcher-start tool) | mounting a watcher equivalent to an active registry entry | duplicate heartbeats after an assumed-dead clock (law-007) |
| `prereg_gate.py` | `Workflow` (Bash wiring is deliberately not shipped: too many false positives on ordinary commands) | anything that looks like an experiment and references no *sealed* pre-registration | three benchmark rounds run without sealing one |
| `decision_card.py` | (checker, not a hook) | a decision card missing any of five elements; more than three open cards | operator cognitive overload (law-006) |

| `dispatch_rung.py` | `Agent` / `Workflow` (**opt-in**, warn by default) | a subagent dispatch whose prompt declares no `RUNG:` and reason | the worker pool died and the agent fell back to the flagship model silently (law-009) |

## Writing a new gate

1. Start from an incident, not from a fear. Put the incident in the docstring.
2. Decide the narrowest pattern that catches it. False blocks erode trust in every gate.
3. Allow on parse failure. Log it.
4. Give the agent the *correct* command in the block message, not just "no".
5. Register it in `laws/` with `enforced_by.kind = gate` so the lineage is kept.
