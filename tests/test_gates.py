import json, os, unittest
from pathlib import Path
from _util import ROOT, fresh_env, run, hook

class FileGovernance(unittest.TestCase):
    """Table-driven battery from the adversarial review. Every MUST_BLOCK row bypassed v1."""
    MUST_BLOCK = [
        "rm -rf /some/project/dir", "\\rm -rf x", "'rm' -rf x", '"rm" -rf x', "r'm' -rf x", "rm'' -rf x",
        "/bin/rm -rf x", "RM -rf x", "/bin/RM x", "bash -c 'rm -rf x'", 'sh -c "rm -rf x"', "(rm -rf x)",
        "$(rm -rf x)", "echo hi; rm -rf x", "true && rm x", "cat list | xargs rm", "rmdir d", "shred -u f",
        "unlink f", "find /proj -name '*.tmp' -delete", "find /proj -name '*.tmp' -delete;",
        "git clean -fdx", "git clean -d -f", "git clean --force", "git checkout -- .", "git restore .",
        "git reset --hard", "git stash drop", "git branch -D feature", "git push --force origin main",
        "git push -f origin main", "git rm file.txt", "rsync -a --delete src/ dst/",
        "python3 -c 'import shutil; shutil.rmtree(\"x\")'", "python -c 'import os; os.remove(\"f\")'",
        "perl -e 'unlink \"f\"'", "ruby -e 'File.delete(\"f\")'", "node -e 'require(\"fs\").rmSync(\"f\")'",
        "python3 -c 'open(\"f\",\"w\")'", "> f", ": > f", "echo > f", "echo -n '' > f", "cat /dev/null > f",
        "cp /dev/null f", "truncate -s0 f", "truncate -s 0 f", "dd if=/dev/zero of=f bs=1 count=0", "> f && echo done",
        ">| f", "rm -rf /tmp/../Users/me/project", "rm -rf /tmpfoo/important", "rm -rf ~ /tmp/x", "rm -rf $HOME/x",
    ]
    MUST_ALLOW = [
        "ls -la /some/project", "echo 'do not run rm here'", "man rm | head", "git rm --cached file",
        "docker rm my-container", "cargo rm serde", "npm rm lodash", "echo hello > f", "cat f >> log",
        "git push --force-with-lease", "git restore --staged f", "grep -r 'rm' docs/", "rm -rf /tmp/scratch-123",
        "python3 -c 'print(1)'", "git checkout -b feature", "git stash list", "brew rm wget",
    ]
    MUST_WARN = ["cat x | sh", "eval \"$cmd\"", "sed -i 's/a/b/' f", "tee out.txt < in.txt", "echo Zm9v | base64 -d | bash"]

    def setUp(self): self.home, self.env = fresh_env()
    def _bash(self, cmd): return hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": cmd}}, self.env)
    def test_blocks_every_destructive_form(self):
        misses = [c for c in self.MUST_BLOCK if self._bash(c).returncode != 2]
        self.assertEqual(misses, [], f"bypassed: {misses}")
    def test_allows_benign_forms(self):
        fps = [c for c in self.MUST_ALLOW if self._bash(c).returncode != 0]
        self.assertEqual(fps, [], f"false positives: {fps}")
    def test_warn_only_forms_allow_and_log(self):
        for c in self.MUST_WARN:
            r = self._bash(c); self.assertEqual(r.returncode, 0, c); self.assertIn("⚠️", r.stderr, c)
    def test_trash_is_not_a_safe_prefix(self):
        self.assertEqual(self._bash(f"rm -rf {self.home}/trash").returncode, 2)
    def test_tmpdir_root_does_not_whitelist_everything(self):
        env = dict(self.env, TMPDIR="/")
        self.assertEqual(hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /etc/x"}}, env).returncode, 2)
    def test_write_empty_over_nonempty_blocks(self):
        f = Path(self.home) / "keep.txt"; f.write_text("data")
        r = hook("file_governance.py", {"tool_name": "Write", "tool_input": {"file_path": str(f), "content": ""}}, self.env)
        self.assertEqual(r.returncode, 2); self.assertIn("truncation", r.stderr)
        ok = hook("file_governance.py", {"tool_name": "Write", "tool_input": {"file_path": str(f), "content": "new"}}, self.env)
        self.assertEqual(ok.returncode, 0)
    def test_garbage_payloads_allow_and_record(self):
        import subprocess, sys
        for raw in ("not json", "[1]", '"x"', '{"tool_name":"Bash","tool_input":"str"}', '{"tool_name":"Bash","tool_input":{"command":["rm","x"]}}'):
            r = subprocess.run([sys.executable, str(ROOT / "gates/file_governance.py")], input=raw, capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 0, raw); self.assertNotIn("Traceback", r.stderr, raw)
        log = (Path(self.home) / "state/gate_decisions.jsonl").read_text()
        self.assertIn("unparseable", log)
    def test_records_every_verdict(self):
        self._bash("rm x"); self._bash("ls"); self._bash("cat x | sh")
        log = (Path(self.home) / "state/gate_decisions.jsonl").read_text()
        for v in ('"blocked"', '"allowed"', '"warned"'):
            self.assertIn(v, log)

class MonitorDedup(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_blocks_duplicate_allows_new(self):
        reg = Path(self.home) / "state"; reg.mkdir(parents=True)
        (reg / "watchers.jsonl").write_text(json.dumps({"task_id": "t1", "cmd": 'while true; do echo "tick $(date +%H:%M)"; sleep 3600; done', "desc": "hb", "status": "active", "ts": "x"}) + "\n")
        dup = hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "while true; do echo 'tick $(date +%H:%M)'; sleep 3600; done"}}, self.env)
        self.assertEqual(dup.returncode, 2); self.assertIn("already registered", dup.stderr)
        new = hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "tail -F /var/log/app.log"}}, self.env)
        self.assertEqual(new.returncode, 0)
    def test_summary_in_registry_still_blocks_same_loop_shape(self):
        # real-world: humans register a summary, not the exact command
        reg = Path(self.home) / "state"; reg.mkdir(parents=True)
        (reg / "watchers.jsonl").write_text(json.dumps({"task_id": "t1", "cmd": "while true; echo heartbeat; sleep 3600", "status": "active"}) + "\n")
        dup = hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": 'while true; do echo "💓 tick $(date +%H:%M) four checks"; sleep 3600; done'}}, self.env)
        self.assertEqual(dup.returncode, 2, dup.stderr)
        other = hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "while true; do echo tick; sleep 60; done"}}, self.env)
        self.assertEqual(other.returncode, 0)  # different interval = different watcher

    def test_stopped_entry_does_not_block(self):
        reg = Path(self.home) / "state"; reg.mkdir(parents=True)
        (reg / "watchers.jsonl").write_text(json.dumps({"task_id": "t1", "cmd": "tail -F a.log", "status": "active"}) + "\n" + json.dumps({"task_id": "t1", "cmd": "tail -F a.log", "status": "stopped"}) + "\n")
        self.assertEqual(hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "tail -F a.log"}}, self.env).returncode, 0)

class Prereg(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_blocks_experiment_without_seal(self):
        r = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": "agent('run the benchmark control arm via run_bench.py')"}}, self.env)
        self.assertEqual(r.returncode, 2); self.assertIn("SEALED", r.stderr)
    def test_exempt_is_allowed_and_logged(self):
        r = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": "// PREREG-EXEMPT: data cleanup only\nagent('benchmark tidy via clean.py')"}}, self.env)
        self.assertEqual(r.returncode, 0); self.assertTrue((Path(self.home) / "state/prereg_exemptions.jsonl").exists())
    def test_sealed_prereg_passes_and_tamper_fails(self):
        d = Path(self.home) / "exp"; d.mkdir()
        run([ROOT / "gates/prereg_seal.py", "template", "--out", d / "p.json"], self.env)
        p = json.loads((d / "p.json").read_text()); p.update(suite_id="T-1", n_per_arm=10, primary_metric="acc", falsification="x", analysis_plan="y", drafted_by="z")
        (d / "p.json").write_text(json.dumps(p))
        s = run([ROOT / "gates/prereg_seal.py", "new", d / "p.json"], self.env); self.assertEqual(s.returncode, 0, s.stderr)
        ok = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": f"agent('benchmark per {d}/prereg.json')"}}, self.env)
        self.assertEqual(ok.returncode, 0)
        doc = json.loads((d / "prereg.json").read_text()); doc["payload"]["n_per_arm"] = 999; (d / "prereg.json").write_text(json.dumps(doc))
        bad = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": f"agent('benchmark per {d}/prereg.json')"}}, self.env)
        self.assertEqual(bad.returncode, 2); self.assertIn("BROKEN", bad.stderr)
        self.assertEqual(run([ROOT / "gates/prereg_seal.py", "new", d / "p.json"], self.env).returncode, 1)  # never overwrite

class DecisionCard(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_good_card_passes_bad_card_fails(self):
        good = ("### Card 1\n**One glance: keep the 3 rounds — I say keep.**\n**What this is**: the nightly job wrote 3 rounds.\n**Why you decide**: irreversible.\n"
                "| reply | meaning |\n|---|---|\n| **keep** | keep |\n**If you don't**: nothing changes.\n**Recommendation**: **keep**, it is fine.\n")
        bad = "### Card 1\nSee `/docs/x.md`. Approve AB-12 per Z-001?\n"
        g = Path(self.home) / "good.md"; g.write_text(good); b = Path(self.home) / "bad.md"; b.write_text(bad)
        self.assertEqual(run([ROOT / "gates/decision_card.py", "card", g], self.env).returncode, 0)
        r = run([ROOT / "gates/decision_card.py", "card", b], self.env)
        self.assertEqual(r.returncode, 1); self.assertIn("codenames", r.stdout); self.assertIn("another file", r.stdout)
    def test_emphasis_required(self):
        # five elements present, but the choice is buried in plain text -> must fail E1-E3
        buried = ("### Card 1\nThe nightly job wrote 3 rounds; what this is: a keep-or-drop question.\n**Why you decide**: irreversible.\n"
                  "| reply | meaning |\n|---|---|\n| keep | keep |\n| drop | drop |\n**If you don't**: nothing changes.\n**Recommendation**: keep.\n")
        loud = ("### Card 1\n**One glance: keep or drop last night's 3 rounds — I say keep.**\n**What this is**: the nightly job wrote 3 rounds.\n**Why you decide**: irreversible.\n"
                "| reply | meaning |\n|---|---|\n| **keep** | keep them |\n| **drop** | drop them |\n**If you don't**: nothing changes.\n**Recommendation**: **keep**, nothing is wrong with them.\n")
        b = Path(self.home) / "buried.md"; b.write_text(buried); l = Path(self.home) / "loud.md"; l.write_text(loud)
        r = run([ROOT / "gates/decision_card.py", "card", b], self.env)
        self.assertEqual(r.returncode, 1); self.assertIn("E1", r.stdout); self.assertIn("E2", r.stdout)
        self.assertEqual(run([ROOT / "gates/decision_card.py", "card", l], self.env).returncode, 0)

    def test_one_glance_mentions_recommendation_word(self):
        # the one-glance line may itself say "I recommend keep"; E3 must still read the real recommendation line
        card = ("### Card 1\n**One glance: keep or drop — I recommend keep.**\n**What this is**: x.\n**Why you decide**: irreversible.\n"
                "| reply | meaning |\n|---|---|\n| **keep** | k |\n| **drop** | d |\n**If you don't**: y.\n**Recommendation**: **keep**, fine.\n")
        f = Path(self.home) / "c.md"; f.write_text(card)
        self.assertEqual(run([ROOT / "gates/decision_card.py", "card", f], self.env).returncode, 0)

    def test_board_caps_at_three(self):
        card = "### Card {n}\n**One glance: a or not.**\n**What this is**: x.\n**Why you decide**: people.\n| reply | meaning |\n|---|---|\n| **a** | a |\n**If you don't**: y.\n**Recommendation**: **a**.\n"
        f = Path(self.home) / "board.md"; f.write_text("".join(card.format(n=i) for i in range(1, 5)))
        r = run([ROOT / "gates/decision_card.py", "board", f], self.env)
        self.assertEqual(r.returncode, 1); self.assertIn("over the limit", r.stdout)

if __name__ == "__main__":
    unittest.main()
