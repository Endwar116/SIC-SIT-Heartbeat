import json, os, subprocess, sys, unittest
from pathlib import Path
from _util import ROOT, fresh_env, run, hook

class PreregV2(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_plain_commands_not_triggered(self):
        for c in ("git commit -m 'retrieve baseline metrics'", "ls experiments/", "cat docs/treatment_of_nulls.md", "grep blind_spot src/"):
            self.assertEqual(hook("prereg_gate.py", {"tool_name": "Bash", "tool_input": {"command": c}}, self.env).returncode, 0, c)
    def test_sidecar_must_match_and_frozen_must_be_status_line(self):
        d = Path(self.home) / "x"; d.mkdir(); doc = d / "prereg.md"; doc.write_text("# plan\nNOT FROZEN yet\n"); (d / "prereg.md.sha256").write_text("deadbeef  prereg.md\n")
        r = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": f"agent('benchmark control arm per {doc} run.py')"}}, self.env)
        self.assertEqual(r.returncode, 2); self.assertIn("does NOT match", r.stderr)
        doc.write_text("> status: FROZEN\n# plan\n"); os.remove(d / "prereg.md.sha256")
        self.assertEqual(hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": f"agent('benchmark control arm per {doc} run.py')"}}, self.env).returncode, 0)
    def test_path_in_comment_does_not_count(self):
        d = Path(self.home) / "y"; d.mkdir(); doc = d / "FROZEN_plan.md"; doc.write_text("> status: FROZEN\n")
        r = hook("prereg_gate.py", {"tool_name": "Workflow", "tool_input": {"script": f"// see {doc}\nagent('benchmark control arm run.py')"}}, self.env)
        self.assertEqual(r.returncode, 2)

class MonitorV2(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_register_stop_and_similar_tail_not_blocked(self):
        run([ROOT / "gates/monitor_dedup.py", "register", "t1", "tail -F a.log", "--desc", "x"], self.env)
        self.assertEqual(hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "tail -F a.log.2 | grep ERROR"}}, self.env).returncode, 0)
        self.assertEqual(hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "tail -F a.log"}}, self.env).returncode, 2)
        run([ROOT / "gates/monitor_dedup.py", "stop", "t1"], self.env)
        self.assertEqual(hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "tail -F a.log"}}, self.env).returncode, 0)
    def test_tickets_is_not_a_tick(self):
        run([ROOT / "gates/monitor_dedup.py", "register", "t2", "while true; do echo tick; sleep 60; done"], self.env)
        self.assertEqual(hook("monitor_dedup.py", {"tool_name": "Monitor", "tool_input": {"command": "while true; do count tickets; sleep 60; done"}}, self.env).returncode, 0)

class Smoke(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_anchor_emit_check_coverage(self):
        run([ROOT / "ledger/ledger.py", "append", "-"], self.env, stdin=run([ROOT / "ledger/derive.py", "--context", "c", "--action", "a"], self.env).stdout)
        line = run([ROOT / "ledger/anchor.py", "emit", "1"], self.env).stdout.strip(); self.assertTrue(line.startswith("⚓ R1 · seq1 · "))
        f = Path(self.home) / "t.md"; f.write_text(line.replace("R1", "Ｒ１") + "\n")
        self.assertEqual(run([ROOT / "ledger/anchor.py", "check", f], self.env).returncode, 1)
        self.assertEqual(run([ROOT / "ledger/anchor.py", "fix", f], self.env).returncode, 0); self.assertIn(line, f.read_text())
        self.assertIn("coverage          100.0%", run([ROOT / "ledger/anchor.py", "coverage", f], self.env).stdout)
    def test_zombie_open_check_close(self):
        run([ROOT / "heartbeat/zombie.py", "open", "W1", "thing", "--ttl", "0"], self.env)
        r = run([ROOT / "heartbeat/zombie.py", "check"], self.env)
        self.assertEqual(run([ROOT / "heartbeat/zombie.py", "close", "W1", "--receipt", "done, see x"], self.env).returncode, 0)
        self.assertEqual(run([ROOT / "heartbeat/zombie.py", "check"], self.env).returncode, 0)
    def test_legislate_reads_examples_and_counts_debts(self):
        out = run([ROOT / "laws/legislate.py", "list"], self.env).stdout; self.assertIn("law-001", out); self.assertIn("law-010", out)
        n = int(run([ROOT / "laws/legislate.py", "debts", "--count"], self.env).stdout.strip()); self.assertGreaterEqual(n, 2)
        v = run([ROOT / "laws/legislate.py", "validate", ROOT / "laws/examples/law-005.json"], self.env); self.assertEqual(v.returncode, 0)
    def test_health_runs(self):
        r = run([ROOT / "heartbeat/health.py"], dict(self.env, HEARTBEAT_SERVICE_FILTER="^com\\.example\\.nothing$")); self.assertIn("checked", r.stdout)
    def test_install_dry_run_and_check(self):
        sp = Path(self.home) / "settings.json"; sp.write_text("{}")
        r = subprocess.run([str(ROOT / "install/install.sh"), "--settings", str(sp), "--dry-run"], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stdout.count("gates/"), 3)
        subprocess.run([str(ROOT / "install/install.sh"), "--settings", str(sp)], capture_output=True, text=True, env=self.env)
        self.assertEqual(subprocess.run([str(ROOT / "install/install.sh"), "--settings", str(sp), "--check"], capture_output=True, text=True, env=self.env).returncode, 0)
        u = subprocess.run([str(ROOT / "install/install.sh"), "--settings", str(sp), "--uninstall"], capture_output=True, text=True, env=self.env)
        self.assertIn("removed 3", u.stdout); self.assertEqual(json.loads(sp.read_text())["hooks"]["PreToolUse"], [])
    def test_tick_records_a_round(self):
        env = dict(self.env, HEARTBEAT_SERVICE_FILTER="^com\\.example\\.nothing$")
        r = subprocess.run([str(ROOT / "heartbeat/tick.sh")], capture_output=True, text=True, env=env)
        self.assertLessEqual(r.returncode, 1, r.stdout + r.stderr); self.assertIn("laws_debts:", r.stdout)
        self.assertEqual(run([ROOT / "ledger/ledger.py", "verify"], env).returncode, 0)

if __name__ == "__main__":
    unittest.main()


class DispatchRung(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_warn_by_default_block_when_strict(self):
        r = hook("dispatch_rung.py", {"tool_name": "Agent", "tool_input": {"prompt": "summarise this file"}}, self.env)
        self.assertEqual(r.returncode, 0); self.assertIn("RUNG", r.stderr)
        ok = hook("dispatch_rung.py", {"tool_name": "Agent", "tool_input": {"prompt": "RUNG: cheap — mechanical doc draft, worker pool down (529)\nsummarise"}}, self.env)
        self.assertEqual(ok.returncode, 0); self.assertNotIn("⚠️", ok.stderr)
        strict = hook("dispatch_rung.py", {"tool_name": "Workflow", "tool_input": {"script": "agent('x')"}}, dict(self.env, HEARTBEAT_RUNG_STRICT="1"))
        self.assertEqual(strict.returncode, 2)
        self.assertEqual(hook("dispatch_rung.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, self.env).returncode, 0)
        log = (Path(self.home) / "state/gate_decisions.jsonl").read_text(); self.assertIn("rung declared", log); self.assertIn('"warned"', log)
