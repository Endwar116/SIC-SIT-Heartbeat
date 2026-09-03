# Ledger specification — SIC-JS 4.0 rounds, hash-chained (ledger format 2)

## One round = one line

```json
{"ledger_version": 2, "seq": 7, "logged_at": "2026-09-04T01:07:50+00:00",
 "prev_hash": "<64 hex>", "state": { ...SIC-JS 4.0 block... },
 "hash": "<64 hex>",
 "discontinuity": {"reason": "...", "problems": ["..."]},      // only when --allow-discontinuity was used
 "governance_flag": "AI_SELF_CLOSED"}                          // only when task.status is terminal
```

`hash = sha256(canonical(wrapper without "hash"))`. Everything else in the line — `seq`, `logged_at`,
`prev_hash`, `state`, the optional fields — is covered. Editing any byte of any past line breaks every hash
after it. The genesis `prev_hash` is 64 zeros.

**Format 1 (before the 2026-09-04 review)** hashed only `prev_hash + canonical(state)`, leaving `seq` and
`logged_at` forgeable. `verify` still accepts format-1 lines (no `ledger_version` key) under the old rule,
so existing chains keep verifying; new lines are always format 2.

## Canonical form (normative)

These exact Python rules define the bytes that are hashed. A verifier in another language must reproduce them:

| rule | value |
|---|---|
| serialiser | `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)` |
| numbers | Python `json` formatting: `1` and `1.0` are **different**; `NaN`/`Infinity` are rejected (exit 2) |
| strings | NFC-normalised on ingest, before hashing |
| key order | lexicographic by Unicode code point (Python `sort_keys`) |
| encoding | UTF-8 |

This is deliberately *not* RFC 8785 JCS; it is documented so it can be reproduced, and may be replaced by JCS in a
future format version.

## The state block

Seven required top-level keys (schema: `ledger/schema/sic-js-4.0.2.json`):

| key | meaning |
|---|---|
| `sic_version` | `"4.0"` |
| `round` | integer, **must equal previous round + 1** (see continuity) |
| `entity` | `{name, model}` — who wrote this; `name` **must not change** between rounds |
| `state` | `{context, current_action, pending[]}` — the only semantic fields the agent supplies |
| `relation` | `{user, linked_entities[], upstream}`; `upstream` = previous hash prefix, `null` at genesis |
| `event` | `{timestamp, description, trigger}` |
| `intent` | `{user_intent, system_intent, core_question}` |

Optional: `task`, `execution`, `assurance`, `extensions`.

## Continuity and identity (enforced on append)

`append` refuses (exit 2) a round whose `round != prev.round + 1` or whose `entity.name` differs from the previous
round. A deliberate break — migrating an old ledger, restarting numbering — is recorded, not hidden:
`ledger.py append - --allow-discontinuity "<reason>"` writes `discontinuity: {reason, problems}` into the wrapper,
and `verify` accepts that line's break because the break is itself on the record.

## Governance flag

If `task.status` is `completed`, `dismissed` or `archived`, the round is written with
`governance_flag: "AI_SELF_CLOSED"` and a loud warning. Nothing is blocked. Completion is the operator's stamp,
not the agent's claim; the flag makes the claim permanent and visible.

## Concurrency and durability

* Appends hold an exclusive `flock` on `rounds.jsonl.lock` from reading the last line through writing the
  round, `STATE_CURRENT.json` and `events.log`. Two processes cannot interleave.
* The round line is `fsync`ed, then the directory is `fsync`ed.
* `STATE_CURRENT.json` = `{"seq", "hash", "state"}`, replaced atomically (tempfile → fsync → `os.replace`).
* `events.log` gets one human-readable line: `time | R<round> | seq<n> | <hash16> | <action…>`.

The three writes are not one transaction. The documented guarantee: **the ledger is written first**; after a
crash `STATE_CURRENT.json` may lag one round, and `verify` reports that as a failure until the next append.

## Torn tail

If the process dies between `write` and `fsync`, the last line may be a fragment. `read_rounds` detects an
unparseable final line without a trailing newline and refuses to append (exit 1) — appending onto a torn file
would bury the damage. `ledger.py repair --torn-tail` moves the fragment to `ledger/torn/<utc>.fragment`,
truncates the file to the last complete line, and writes a `REPAIR` line to `events.log`. It is the only
sanctioned modification of `rounds.jsonl`, and it leaves evidence.

## What `verify` checks

1. `prev_hash` of each line equals the `hash` of the previous line (genesis: 64 zeros)
2. `hash` recomputes (format 2: whole wrapper; format 1: `prev_hash + state`)
3. `seq` equals the line number
4. `round` increases by exactly 1 unless the line records a `discontinuity`
5. `entity.name` is constant over the last 20 rounds
6. `STATE_CURRENT.json` matches the last round (catches a deleted trailing line and a desync)
7. no torn tail

## What `verify` cannot detect

**Deletion of the trailing N lines together with a matching rewrite of `STATE_CURRENT.json`** is invisible from
inside the directory. The chain is tamper-*evident*, not tamper-*proof*. Mitigation: publish the latest
`hash` somewhere the agent cannot rewrite — the anchor line in a chat transcript, a commit message, a
message to another party. `ledger/anchor.py` prints that line.

## Anchor line

```
⚓ R<round> · seq<n> · <first 16 hex of hash>
```

Half-width digits, lowercase hex, the exact separator ` · `. The emoji is for eyes only and never a search key.
`anchor.py check|fix|coverage` measures and repairs drift; in one real archive 16 % of hand-typed anchors had
drifted and only 1.5 % of rounds were anchored at all — which is why the format is frozen and tooled.

## Worked example (three rounds, hashes abbreviated)

```
{"ledger_version":2,"seq":1,"logged_at":"…","prev_hash":"000…000","state":{"round":1,…},"hash":"3f9a…"}
{"ledger_version":2,"seq":2,"logged_at":"…","prev_hash":"3f9a…","state":{"round":2,…},"hash":"b41c…"}
{"ledger_version":2,"seq":3,"logged_at":"…","prev_hash":"b41c…","state":{"round":3,…},"hash":"7de0…"}
STATE_CURRENT.json = {"seq":3,"hash":"7de0…","state":{"round":3,…}}
```

Change one character in line 2's `state` → line 2's `hash` no longer recomputes, and line 3's `prev_hash` no
longer matches. Change line 2's `seq` to 999 → line 2's hash no longer recomputes (format 2). Delete line 3 →
`STATE_CURRENT.json` points at a hash that is no longer last.

## Truth sources, not memory

| field | derived from | by |
|---|---|---|
| `round` | last round in the ledger + 1 | `derive.py` |
| `relation.upstream` | previous `hash` (16 chars); `null` at genesis | `derive.py` |
| `entity.name` / `entity.model` | `HEARTBEAT_AGENT` / `HEARTBEAT_MODEL` environment — a model cannot attest itself | `paths.py` |
| `event.timestamp`, `logged_at` | system clock | `derive.py` / `ledger.py` |
| `task.*` | inherited from the previous round | `derive.py` |
| `state.context`, `current_action`, `intent.*` | the agent | — |
