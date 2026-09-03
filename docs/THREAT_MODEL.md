# Threat model — what this does and does not guarantee

This document defines the security properties of the heartbeat governance system. It names the assets we protect, the adversaries we consider, and the guarantees and non-guarantees we make.

## Assets

1. **Ledger integrity**: The append-only log of agent decisions. An edit to the ledger is detectable; the log is authoritative for what the agent claimed, when, and what state it was in.

2. **Reversibility of deletions**: Items soft-deleted via `tombstone.py trash` are recoverable. The deletion itself is logged with metadata (who, when, why) and a SHA256 manifest proves nothing was silently corrupted.

3. **Gate decisions**: Every decision by a gate (allow or block) is recorded in `state/gate_decisions.jsonl`. A policy can be audited by reading what was actually enforced, not what was configured.

## Adversaries considered

We defend against:

1. **A mistaken agent**: The agent follows policy correctly but makes a semantic error (wrong task marked complete, wrong item deleted). The ledger records what it did; the operator can audit, revoke, and correct.

2. **An agent rationalizing around a rule**: The agent is not blocked; it does what it likes. Governance relies on gates, post-hoc audit, and human override. The ledger records the attempt; laws and gates decide the consequence.

3. **Operator error**: A human accidentally appends a malformed round or deletes a file. Verification catches corruption. Tombstones and restore procedures let us recover from accidental deletion.

4. **Crash mid-write**: The process dies in the middle of appending a round or replacing `STATE_CURRENT.json`. Atomic writes (tempfile + fsync + os.replace) ensure the ledger and current state never contradict each other. A crash leaves one or the other unchanged; recovery is deterministic.

## Adversaries not considered

We do **not** defend against:

1. **Compromised host or root access**: If someone gains shell access to the machine, they can edit the ledger file, rewrite history, or delete everything. No software-based hash chain can protect data from root.

2. **Malicious human with write access to the ledger file**: If an operator or insider with filesystem access decides to forge a round, edit hashes, or delete trailing lines, they can. The hash chain is **tamper-evident, not tamper-proof**. We can detect the edit after the fact if we have an external anchor (e.g., a published hash). We cannot prevent it.

3. **Network attackers**: This system is local-disk-only. There is no remote storage, no replication, and no network protocol. Network security is out of scope.

## Guarantees

The system **does** provide:

1. **Append-only detection of edits**: Any byte changed in any past round breaks all downstream hashes. Run `verify` to detect the first point of corruption.

2. **Recomputable chain**: Given the full ledger and the first prev_hash (64 zeros), you can recompute every hash independently. If your computation matches the stored hash, the round has not been edited.

3. **Atomic current state**: `STATE_CURRENT.json` is always consistent with the last appended round. No partial writes, no orphaned temp files.

4. **Reversible deletes with SHA256 manifest**: Every soft-deleted item is moved to `trash/<timestamp>_<name>/` with a `TOMBSTONE.md` (metadata) and `MANIFEST.sha256.json` (file hashes). Restore is a single command. A human must empty the trash; the agent cannot.

5. **Gate decisions logged**: Every gate (allow, block, warn) is appended to `state/gate_decisions.jsonl` with timestamp, gate name, verdict, and reason. Policy enforcement is auditable.

6. **Fail-open gates never crash-block**: If a gate script crashes, throws an exception, or cannot read its input, it **allows** the action and logs the anomaly. A gate bug will not mysteriously block your agent. You will see the anomaly in the logs and can investigate.

## Non-guarantees

The system does **not** provide:

1. **Detection of deleted trailing lines without an external anchor**: If someone removes the last N lines from `rounds.jsonl`, the remaining log is internally consistent (each hash matches its prev_hash). Verification passes. To detect this, you must publish the latest hash somewhere external (e.g., a git commit, a public archive, or a timestamp service) and check on audit whether the ledger's latest hash matches. Without an external anchor, you cannot prove trailing rounds were not deleted.

2. **Gates cannot be bypassed if hooks are disabled**: If the harness (Claude Code, a custom agent runner, etc.) does not call the gate on a tool use, the gate has no effect. An operator with access to the harness config can disable hooks. This is acceptable: gates are a policy layer, not a cryptographic proof.

3. **The local model/harness may lie about entity.model**: The `entity.model` field is set by the harness environment variable (`HEARTBEAT_MODEL`), not by the model itself. A harness can claim the agent is running under any model name. This is intentional: a model cannot attest its own identity, and we rely on the operator to set this truthfully. If you see a mismatch, check the harness config.

4. **The trash can be emptied by a human**: A human with filesystem access can delete the `trash/` directory, removing all tombstones and manifests. Once the trash is empty, deleted items cannot be restored. This is by design: only humans, not the agent, can permanently destroy data. If recovery is critical, back up the trash separately.

## Git history is the product {#history}

When this ledger system is integrated into a larger project with version control, **internal files must never be staged into a public repository** before publication.

### The problem

If internal ledger entries, laws, incident records, or other governance logs enter the public git history before you intend to publish them:

- **Deleting the file from HEAD is not a fix.** The file is still in every earlier commit. Anyone with read access to the repository can retrieve it.
- **Rewriting history is the only remedy.** You must rebase, filter, or squash commits to remove the file from *all* commits, not just the latest.

### The solution

Before publishing a public repository (on GitHub, GitLab, or any public forge), run:

```bash
git log -p --  # View all changes, line by line, for every commit
```

Scan for:
- Ledger files (rounds.jsonl, STATE_CURRENT.json, events.log)
- Trash entries and tombstones
- Law records and incident logs
- Gate decisions or governance metadata
- Any file path under an internal state directory

If you find sensitive internal files in the history, rewrite it:

```bash
git filter-repo --path <internal-file> --invert-paths   # never filter-branch; never a deletion commit
# or use git filter-repo (faster, more flexible)
git filter-repo --path path/to/internal/file --invert-paths
```

Then force-push (if you own the repository):

```bash
git push origin --force-all --force-tags
```

Notify users who have cloned the old history; they should re-clone after the rewrite.

### The rule

- **Internal governance logs are internal.** Do not stage them.
- **If you stage them by accident, rewrite history.** Deleting from HEAD is not enough.
- **Scan all commits before publishing.** Use `git log -p` to verify, not just `git status HEAD`.
- **This is a one-time check per repository.** After you publish, the history is part of the public record.


## Hand-delivered bundles {#deliverables}

If you ever ship a de-identified copy of a real installation (a zip to a colleague), three things bit us on the
first day (law-011):

1. **Scan the artifact, not the source.** Unpack the bundle and grep the whole thing. Keep an explicit
   allow-list of the lines that may match (the LICENSE copyright, a scanner's own regex source) and abort on
   anything else — with an explicit `exit 1`, not `set -e`.
2. **The redaction log must not contain the redacted strings.** Record the category and a `sha256` prefix of
   the original; the holder of the original environment can still reconcile, nobody else can.
3. **A check instruction must not quote the forbidden pattern.** "Run `grep -rn "<secret words>"` before
   publishing" puts the secret words in the document. Point at where the pattern lives instead.
