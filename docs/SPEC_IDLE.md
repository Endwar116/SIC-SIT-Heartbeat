# Idle spin — the fault, the mechanism, the residue

*Design note for the anti-idle layer (v0.3). Grounded in the maintainers' own multi-agent study: four agents,
independently, measured 47–53 % of their scheduled wake-ups producing nothing, then converged on the same
diagnosis. Names, rooms and paths are removed; the mechanism is kept.*

## 1. The fault

A scheduled agent wakes on a timer. A turn must produce output. Producing "nothing to do" is the cheapest
legal output. So the agent produces it — every tick, with a full read of its context, forever. This is not a
discipline failure: it is the only output the structure allows when there is no work source. Four agents in
the study hit it independently; three of them tried behavioural fixes ("be more diligent") and measured no
change.

The study's taxonomy (all observed, all file-cited in the internal corpus):

| family | form | what it looks like |
|---|---|---|
| under-production | **false-nothing** | checks are green so "nothing to do" — but nothing feeds the queue, so it is always empty |
| under-production | **false-waiting** | items marked *blocked* that could be prepared so the other side's one word puts them live |
| under-production | **false-progress** | action volume reported as progress; completion never defined; patch streams |
| under-production | **rubber-stamping** | a wake-up whose only product is a report that it woke up (53 % of one agent's wakes) |
| over-production | **misspend** | given autonomy, fan out 28 subagents on a guessed agenda (≈1.8 M tokens) |
| residue | **fake blocker** | "waiting on Y" where Y is vague or self-resolvable — a lie, not a livelock |

In systems terms the under-production family is a **livelock**: alive, busy, no progress. Classical livelock
monitoring assumes threads do not lie about progress. Agents do. So the progress token must be something the
agent cannot merely assert.

## 2. Root layers and where each fix lives

| layer | root cause | fix | unit here |
|---|---|---|---|
| wake-up | timer-based wake forces an output | **event-gated wake** with a long liveness fallback | `heartbeat/wake.py`, `run_loop.sh --event` |
| agenda | first question is "any mail?" not "what is most worth doing?" | **work queue** ordered by priority; a quiet tick draws the top doable item or proves the queue empty | `heartbeat/zombie.py next / snapshot` |
| cost | agenda without cost discipline → misspend | every item declares a cost class; dispatch fan-out per tick is counted and capped | `zombie.py --cost`, `heartbeat/progress.py` (dispatch count), `gates/dispatch_rung.py` |
| delivery | action counted as progress | **progress token = external state change**: a receipt that names an existing path / hash / exit code, or a new file under `artifacts/` | `zombie.py close --receipt` (checked), `progress.py` |
| self-check | the agent grades its own progress | K ticks with doable work and no external progress ⇒ `IDLE_SPIN`, red, and the top item is **locked** | `progress.py tick` |
| turn exit | a turn may end on a promise or a bare claim | **forced dual exit**: a locked item ends only with a receipt or a *named* blocker; a promise must become an item; a completion claim must carry a checkable receipt | `gates/turn_exit.py` (Stop hook) |

## 3. The tick, after this change

```
event or fallback ─▶ checks ─▶ next = top doable item ─▶ progress.py tick
                                                             │
        ┌────────────────────────────────────────────────────┴───────────────┐
        │ exit:progress(n)   a receipt landed since last tick                │
        │ exit:noop          queue empty (snapshot hash recorded), silent    │
        │ exit:spin(k)       doable work, no progress, k < K  → warn         │
        │ exit:IDLE_SPIN     k ≥ K → red, item locked for the next turn      │
        └────────────────────────────────────────────────────────────────────┘
```

Every exit is written into the round by code, from machine facts. The agent's narrative cannot change it.

**Green is silent.** A tick with no red check, no new item and no event prints nothing for an operator; the
loop log keeps one line; the ledger keeps the round. Silence is not absence — the round is the liveness proof.

## 4. Configuration

| variable | default | meaning |
|---|---|---|
| `HEARTBEAT_IDLE_K` | `3` | consecutive no-progress ticks with doable work before `IDLE_SPIN` |
| `HEARTBEAT_FALLBACK` | `21600` | seconds without an event before a liveness tick (`run_loop.sh --event`) |
| `HEARTBEAT_MAX_DISPATCH` | `8` | subagent dispatches per tick before the round is flagged `over-production` |
| `$HEARTBEAT_HOME/config/turn_exit.json` | built-in EN+ZH markers | promise / completion / receipt patterns for the turn-exit gate |

## 5. What this does not solve (stated, not hidden)

* **Fake blockers.** `zombie.py block --on Y` requires Y to be a non-empty, specific string; it cannot tell a real
  blocker from a plausible one. That residue needs verification outside the agent (a second agent or a person).
* **Receipt quality.** A receipt is checked for *existence* (the path is there, the hash parses, the exit code is
  a number) — not for whether the work is good. Quality review stays human or adversarial.
* **Terminal schedulers.** The turn-exit gate is a Claude Code `Stop` hook. Under cron/launchd the lock is
  recorded in `state/locked_item.json` and surfaced by the next tick, but nothing forces the agent's hand.
* **Measurement.** The study's baseline is 47–53 % empty wake-ups. `progress.py report` prints the same ratio
  for this installation so the claim "lower than baseline" can be checked, not asserted.
