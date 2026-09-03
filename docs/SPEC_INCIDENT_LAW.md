# Incident → Law → Gate

Most agent-governance material is written *before* anything goes wrong. This pipeline is written
*after*. Each law in `laws/examples/` is a real operating incident, de-identified, with the
mechanism preserved.

## Shape of a law (`laws/LAW_SCHEMA.json`)

```
incident   when / what happened / how it was noticed (or why it was not)
root_cause one sentence
law        imperative text + checkable conditions
enforced_by gate | checker | procedure | none-yet   (+ path)
lineage    incident → law → gate
```

`none-yet` is allowed and visible. A law nobody enforces is a debt, and `legislate.py debts` keeps
it in view. The failure mode this prevents is the most common one: a lesson written into a document
that never fires again.

## Two laws worth reading first

**law-007 — peripheral signals open an investigation, they never close it.**
Exit codes, "is the process running", "does the log exist" are symptoms. The subject's own record
(its run log, its state file) is the chart. Read the chart before pronouncing. Rule out "it finished
on purpose" before "it died". The maintainers misdiagnosed a completed 12-run job as "never ran" by
skipping this step, and announced it to the job's owner. `heartbeat/health.py` prints this reminder
after every red result for that reason.

**law-008 — check rule provenance before claiming authority.**
When an agent holds delegated authority, the dangerous failure is not timidity; it is deciding
something that was never its to decide, while feeling certain. Intuition ("this feels internal") was
wrong 3 times out of 3 in the incident. Look in three places before reclaiming an item: hard rules in
code, standing orders and freezes (especially the operator's own), approval conditions written into
the item's design. Any hit → hand it back.

## Numbers (law-003) {#numbers}

A number in a report is written next to the command that produced it and that command's output.
Release verification runs in a fresh clone. "130+" became 103 under recount; the fix is not care, it
is a rule that removes the opportunity.

## Authority (law-008) {#authority}

List "decided" and "executed" separately. All three mis-reclaimed items in the incident were caught
*because* they sat in the "decided, not yet executed" column long enough to be checked. Collapsing the
two columns into "done" would have executed all three.

## Legislating

```
python3 laws/legislate.py new \
  --what   "what happened, plainly" \
  --signal "how it was noticed" \
  --cause  "one sentence" \
  --text   "the rule, imperative" \
  --check  "a checkable condition" --check "another" \
  --enforce gate --ref gates/your_gate.py
```

The heartbeat records the law's id in the round in which it was legislated, so the ledger answers
"what did we learn, and when".
