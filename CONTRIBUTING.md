# Contributing

**Start from an incident.** The unit of contribution here is not a feature; it is a failure that has
been turned into a rule. A pull request that adds a gate should carry the law that motivated it
(`laws/examples/law-NNN.json`) and a test that shows the gate firing on the incident's shape.

Rules we hold ourselves to (they are also laws in `laws/examples/`):

* **Numbers are measured next to where they are written** (law-003). If you claim "19 tests", the
  PR shows the command and its output.
* **Decided ≠ executed** (law-008). A PR description lists what was decided and what was actually
  done as separate lists.
* **Peripheral signals open, records close** (law-007). Bug reports about "the service is dead"
  include the service's own log/state, not only `launchctl list`.
* **No hard deletes in the repo history** (law-004). If a file with internal content was ever
  committed, the fix is a history rewrite before publication, not a deletion commit.

Practical:

* Standard library only. A dependency needs a reason written into the PR.
* Gates must allow on parse failure and finish in well under 500 ms.
* `python -W error::ResourceWarning -m unittest discover -s tests` must pass on 3.9 and 3.12.
* De-identify. No personal names, no machine paths, no organisation-internal constants in
  code, docs, tests, or commit messages.

By contributing you agree your contribution is licensed under the MIT License.
