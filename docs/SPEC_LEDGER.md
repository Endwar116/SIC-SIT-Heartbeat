# Ledger specification (SIC-JS 4.0 rounds, hash-chained)

## Overview

The ledger is an append-only, hash-chained log of autonomous agent decisions. Each round (one heartbeat tick) is recorded as a single JSON line in `rounds.jsonl`, called a *wrapper*. The wrapper contains a sequence number, timestamp, the cryptographic hash of that round, the hash of the previous round, and the SIC-JS 4.0 state block itself. Any edit to a past round is immediately detected because every subsequent hash becomes invalid.

## Wrapper line format

Each line in `rounds.jsonl` is a JSON object (wrapper) with exactly these keys:

```
{
  "seq":       integer (monotonic, starting 1),
  "logged_at": ISO 8601 timestamp,
  "hash":      sha256 hex digest (64 lowercase chars),
  "prev_hash": sha256 hex digest (64 lowercase chars),
  "state":     SIC-JS 4.0 state block
}
```

Optional: `"governance_flag": "AI_SELF_CLOSED"` is added when the agent marks a task as `completed`, `dismissed`, or `archived`. This flag is recorded but does not block the round — governance is enforced by gates, not by ledger rejection.

## Hash computation

```
hash = sha256(prev_hash + canonical(state))
```

where `canonical(state)` is:

```python
json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
```

- **Sort keys**: alphabetically by key name at every level of nesting (deterministic).
- **ensure_ascii=False**: UTF-8 characters are not escaped; they appear literally in the hash input.
- **Separators**: exactly `(",", ":")` with no whitespace (compact form).

### Genesis

The first round has `prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"` (64 ASCII zeros).

### Chain integrity

Because each hash includes the previous hash, editing any byte in any past round breaks all downstream hashes. This is detectable by recomputing: `hash = sha256(prev_hash + canonical(state))` for every round and comparing to the stored hash.

## SIC-JS 4.0 state block: required and optional keys

The `state` field must be a JSON object containing these seven required top-level keys:

| Key | Type | Meaning |
|---|---|---|
| `sic_version` | string | Schema version; must be `"4.0"` |
| `round` | integer | Monotonic round number; must equal previous round + 1 |
| `entity` | object | Identity of the agent: `{"name": "...", "model": "..."}` |
| `state` | object | The agent's semantic state: context, current action, pending items |
| `relation` | object | Links and upstream hash: `{"upstream": "<hash or 'genesis'>", "user": "...", "linked_entities": [...]}` |
| `event` | object | What triggered this round: `{"timestamp": "...", "description": "...", "trigger": "..."}` |
| `intent` | object | Agent and user intents: `{"user_intent": "...", "system_intent": "...", "core_question": "..."}` |

Optional keys (present only if needed):

- `task`: Task metadata (id, title, status, deliverable, created_round). If `status` is a terminal state (completed, dismissed, archived), the wrapper gains `governance_flag: AI_SELF_CLOSED`.
- `execution`: How the action was carried out.
- `assurance`: Evidence and approval metadata (required when `task.status = "completed"`).
- `extensions`: Array of extension objects for domain-specific fields.

## Governance flag: AI_SELF_CLOSED

When a round is appended with `task.status` in `{"completed", "dismissed", "archived"}`, the ledger:

1. **Records** the governance flag in the wrapper: `"governance_flag": "AI_SELF_CLOSED"`
2. **Does NOT block** the round — the append succeeds
3. **Warns loudly** to stderr: a governance decision was made by the agent, not by a human

The rule: completion is a stamp, not a claim. Operator or designated verifier closes work. The flag is a permanent record that this rule was crossed; gates and policy enforcement decide what happens next.

## Atomic current state

After every round is appended, `STATE_CURRENT.json` is replaced atomically:

1. Write to a temporary file (suffix `.json`, in the same directory as `STATE_CURRENT.json`)
2. Call `fsync()` on the file descriptor to ensure the OS buffer is written to disk
3. Call `os.replace()` to atomically rename the temp file to `STATE_CURRENT.json`

This ensures that even if the process crashes between append and replacement, the ledger and current state never contradict each other.

## Events log digest

After each round, a human-readable one-liner is appended to `events.log`:

```
<logged_at> | R<round> | seq<seq> | <hash_first_16_chars> | <digest>
```

Example:
```
2026-09-04T14:30:45+02:00 | R42 | seq142 | a1b2c3d4e5f6g7h8 | Processed 3 tasks, 1 blocked
```

The digest is the first 160 characters of `state.state.current_action`, with newlines replaced by spaces.

## Anchor line format

An anchor is a compact, immutable reference to a specific round. It appears at the end of agent output and is suitable for printing, sharing, or publishing:

```
⚓ R<round> · seq<seq> · <hash_first_16_chars>
```

Example:
```
⚓ R42 · seq142 · a1b2c3d4e5f6g7h8
```

### Why exact format matters

- **Half-width digits and spacing**: The anchor must be copy–paste-able and unambiguous in any font or terminal.
- **Lowercase hex**: The hash is always lowercase; uppercase is reserved for other uses.
- **First 16 characters of hash**: A strong enough collision guard for human identification while remaining short.

If you publish this anchor elsewhere (e.g., a public log or archive), readers can later ask: "Does round 42, seq 142 in your ledger have hash starting `a1b2c3d4e5f6g7h8`?" If it doesn't, the ledger was edited after the anchor was published.

## Verification: what detect and what not

### What `verify` detects

`ledger.py verify` recomputes every hash and checks every `prev_hash` link:

- ✓ **Any byte edited** in any past state block
- ✓ **Any hash value** that was hand-edited or corrupted
- ✓ **Any prev_hash** that no longer points to the previous round's hash
- ✓ **Parsing errors** in any JSON line (corrupt round)
- ✓ **First occurrence** of a break in the chain (reports: line number, seq, expected vs. stored)

### What `verify` cannot detect

- ✗ **Trailing lines deleted**: If the last N lines are removed entirely, verification still passes on what remains. This is a fundamental property of append-only logs: deletion is undetectable without an external anchor (see below).
- ✗ **Lines inserted in the middle**: If a line is inserted, the downstream `prev_hash` values no longer match their predecessors — but the hash of the inserted line itself is unverified. Verification detects the break; it does not identify which line is fake.

### Mitigation for deleted trailing lines

Publish the latest anchor hash somewhere external and immutable (e.g., a git commit message, a public log, a timestamp service). On audit, check whether the ledger's latest hash matches the published anchor. If the ledger is shorter, trailing rounds were deleted. If the hash does not match, the state was edited.

## Worked example

Below are three consecutive rounds (simplified; hashes are placeholders).

```json
{"seq":1,"logged_at":"2026-09-04T10:00:00+00:00","hash":"a1b2c3d4e5f6f7f8f9fafbfcfdfeff00a1b2c3d4e5f6f7f8f9fafbfcfdfeff0","prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","state":{"sic_version":"4.0","round":1,"entity":{"name":"heartbeat","model":"claude-3-5-sonnet-20241022"},"state":{"context":"System startup","current_action":"Initialize","pending":[]},"relation":{"upstream":"genesis","user":"operator","linked_entities":[]},"event":{"timestamp":"2026-09-04T10:00:00+00:00","description":"Initialize","trigger":"startup"},"intent":{"user_intent":"Start agent","system_intent":"Bootstrap","core_question":"Is system ready?"}}}
```

```json
{"seq":2,"logged_at":"2026-09-04T10:05:00+00:00","hash":"b2c3d4e5f6f7f8f9fafbfcfdfeff00a1b2c3d4e5f6f7f8f9fafbfcfdfeff00b2c3d4e5","prev_hash":"a1b2c3d4e5f6f7f8f9fafbfcfdfeff00a1b2c3d4e5f6f7f8f9fafbfcfdfeff0","state":{"sic_version":"4.0","round":2,"entity":{"name":"heartbeat","model":"claude-3-5-sonnet-20241022"},"state":{"context":"Running checks","current_action":"Verify services","pending":["check_inbox","scan_zombies"]},"relation":{"upstream":"a1b2c3d4e5f6f7f8","user":"operator","linked_entities":[]},"event":{"timestamp":"2026-09-04T10:05:00+00:00","description":"Verify services","trigger":"heartbeat"},"intent":{"user_intent":"Monitor health","system_intent":"Detect anomalies","core_question":"Are services healthy?"}}}
```

```json
{"seq":3,"logged_at":"2026-09-04T10:10:00+00:00","hash":"c3d4e5f6f7f8f9fafbfcfdfeff00a1b2c3d4e5f6f7f8f9fafbfcfdfeff00b2c3d4e5c3d4e5f6","prev_hash":"b2c3d4e5f6f7f8f9fafbfcfdfeff00a1b2c3d4e5f6f7f8f9fafbfcfdfeff00b2c3d4e5","state":{"sic_version":"4.0","round":3,"entity":{"name":"heartbeat","model":"claude-3-5-sonnet-20241022"},"state":{"context":"Decision point","current_action":"Mark task as in_progress","pending":[]},"relation":{"upstream":"b2c3d4e5f6f7f8f9","user":"operator","linked_entities":[]},"event":{"timestamp":"2026-09-04T10:10:00+00:00","description":"Mark task as in_progress","trigger":"gate_allow"},"intent":{"user_intent":"Proceed","system_intent":"Execute gated action","core_question":"Is action permitted?"},"task":{"id":"T-001","title":"Daily check","deliverable":"Report","status":"in_progress","created_round":2}}}
```

Note: The hashes are illustrative. A real hash is exactly 64 hexadecimal characters (0–9, a–f). To compute the actual hash for round 2, you would:

```python
import hashlib, json
prev_hash = "a1b2c3d4e5f6f7f8f9fafbfcfdfeff00a1b2c3d4e5f6f7f8f9fafbfcfdfeff0"
state = { "sic_version": "4.0", "round": 2, ... }  # the state from round 2
canonical = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
hash_hex = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()
```

## Truth sources

The ledger is derived from sources of truth, not from agent memory. This table shows which fields are recomputed by code and which are supplied by the agent:

| Field | Source | Why |
|---|---|---|
| `round` | Last round in ledger + 1 | Agents miscount from memory |
| `relation.upstream` | Recomputed hash of previous round (first 16 chars) | Never trust a model-computed hash |
| `entity.name` | Installation config (`HEARTBEAT_AGENT` environment variable) | A global identity must be immutable |
| `entity.model` | Harness environment (`HEARTBEAT_MODEL` environment variable) | A model cannot attest its own identity |
| `event.timestamp` | System clock (UTC, local timezone applied) | Hand-written timestamps drift |
| `task.*` | Inherited from previous round | Inheritance is copying, not remembering |
| `state.context` | Agent (semantic field) | Code cannot derive meaning |
| `state.current_action` | Agent (semantic field) | Code cannot derive meaning |
| `state.pending` | Agent (semantic field) | Code cannot derive meaning |
| `intent.*` | Agent (semantic fields) | Code cannot derive meaning and does not pretend to |

This design ensures that an audit of the ledger is an audit of the agent's actual decisions, not a test of its memory.
