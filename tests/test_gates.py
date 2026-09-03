import json, os, unittest
from pathlib import Path
from _util import ROOT, fresh_env, run, hook

class FileGovernance(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_blocks_rm(self):
        r = hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /some/project/dir"}}, self.env)
        self.assertEqual(r.returncode, 2); self.assertIn("hard delete", r.stderr); self.assertIn("tombstone.py", r.stderr)
    def test_allows_ls(self):
        r = hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": "ls -la /some/project"}}, self.env)
        self.assertEqual(r.returncode, 0)
    def test_allows_rm_in_tmp(self):
        r = hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/scratch-123"}}, self.env)
        self.assertEqual(r.returncode, 0)
    def test_blocks_find_delete_and_git_clean(self):
        for c in ("find /proj -name '*.tmp' -delete", "git clean -fdx"):
            self.assertEqual(hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": c}}, self.env).returncode, 2, c)
    def test_ignores_other_tools_and_garbage(self):
        self.assertEqual(hook("file_governance.py", {"tool_name": "Read", "tool_input": {}}, self.env).returncode, 0)
        import subprocess, sys
        r = subprocess.run([sys.executable, str(ROOT / "gates/file_governance.py")], input="not json", capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0)
    def test_records_decisions(self):
        hook("file_governance.py", {"tool_name": "Bash", "tool_input": {"command": "rm x"}}, self.env)
        log = Path(self.home) / "state/gate_decisions.jsonl"
        self.assertTrue(log.exists()); self.assertIn('"verdict": "blocked"', log.read_text())

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
        r = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": "agent('run the benchmark control arm')"}}, self.env)
        self.assertEqual(r.returncode, 2); self.assertIn("SEALED", r.stderr)
    def test_exempt_is_allowed_and_logged(self):
        r = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": "// PREREG-EXEMPT: data cleanup only\nagent('benchmark tidy')"}}, self.env)
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
        bad = "### Card 1\nSee `/docs/x.md`. Approve VS-13 per D-004?\n"
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
