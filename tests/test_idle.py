import json, os, time, unittest
from pathlib import Path
from _util import ROOT, fresh_env, run, hook

Z = ROOT / "heartbeat" / "zombie.py"
P = ROOT / "heartbeat" / "progress.py"
W = ROOT / "heartbeat" / "wake.py"
T = ROOT / "heartbeat" / "tick.sh"


def rounds(d):
    p = Path(d) / "ledger" / "rounds.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


class QueueTests(unittest.TestCase):
    def test_open_defaults_to_doable_and_next_returns_it(self):
        d, env = fresh_env()
        self.assertEqual(run([Z, "open", "a1", "write the spec"], env).returncode, 0)
        r = run([Z, "next"], env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["id"], "a1")

    def test_waiting_item_needs_a_pre_doable(self):
        d, env = fresh_env()
        r = run([Z, "open", "w1", "wait for the reviewer", "--pile", "others"], env)
        self.assertNotEqual(r.returncode, 0)
        r = run([Z, "open", "w1", "wait for the reviewer", "--pile", "others", "--pre", "draft the reply so one word puts it live"], env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(run([Z, "next"], env).stdout.strip(), "")  # others-pile items are not "next"

    def test_priority_then_age(self):
        d, env = fresh_env()
        run([Z, "open", "old-p2", "older P2"], env); time.sleep(0.01)
        run([Z, "open", "new-p0", "newer P0", "--priority", "P0"], env)
        self.assertEqual(json.loads(run([Z, "next"], env).stdout)["id"], "new-p0")

    def test_close_requires_a_checkable_receipt(self):
        d, env = fresh_env()
        run([Z, "open", "c1", "make a file"], env)
        r = run([Z, "close", "c1", "--receipt", "done, trust me"], env)
        self.assertNotEqual(r.returncode, 0)
        f = Path(d) / "artifact.txt"; f.write_text("x")
        r = run([Z, "close", "c1", "--receipt", f"wrote {f}"], env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run([Z, "next"], env).stdout.strip(), "")

    def test_block_needs_a_concrete_reason_and_moves_the_item(self):
        d, env = fresh_env()
        run([Z, "open", "b1", "needs an answer"], env)
        self.assertNotEqual(run([Z, "block", "b1", "--on", ""], env).returncode, 0)
        self.assertEqual(run([Z, "block", "b1", "--on", "operator must pick A or B (asked 2026-09-05)"], env).returncode, 0)
        snap = json.loads(run([Z, "snapshot"], env).stdout)
        self.assertEqual(snap["doable"], 0); self.assertEqual(snap["operator"] + snap["others"], 1)

    def test_snapshot_hash_proves_emptiness(self):
        d, env = fresh_env()
        s1 = json.loads(run([Z, "snapshot"], env).stdout)
        self.assertEqual(s1["doable"], 0); self.assertEqual(len(s1["sha256"]), 64)
        run([Z, "open", "x", "x"], env)
        self.assertNotEqual(json.loads(run([Z, "snapshot"], env).stdout)["sha256"], s1["sha256"])


class ProgressTests(unittest.TestCase):
    def test_streak_grows_only_with_doable_work_and_no_progress(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "3"
        run([Z, "open", "p1", "do it"], env)
        codes = [run([P, "tick"], env).returncode for _ in range(3)]
        self.assertEqual(codes, [0, 0, 1])                       # third quiet tick with doable work = IDLE_SPIN
        st = json.loads((Path(d) / "state" / "progress.json").read_text())
        self.assertEqual(st["streak"], 3)
        self.assertTrue((Path(d) / "state" / "locked_item.json").exists())

    def test_receipt_resets_the_streak(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "2"
        run([Z, "open", "p1", "do it"], env)
        run([P, "tick"], env)
        f = Path(d) / "out.txt"; f.write_text("ok")
        run([Z, "close", "p1", "--receipt", f"wrote {f}"], env)
        r = run([P, "tick"], env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("exit:progress", r.stdout)

    def test_empty_queue_is_noop_not_spin(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "1"
        for _ in range(3):
            r = run([P, "tick"], env)
            self.assertEqual(r.returncode, 0); self.assertIn("exit:noop", r.stdout)

    def test_report_ratio(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "9"
        run([Z, "open", "p1", "do it"], env)
        for _ in range(4): run([P, "tick"], env)
        rep = json.loads(run([P, "report"], env).stdout)
        self.assertEqual(rep["ticks"], 4); self.assertEqual(rep["empty"], 4); self.assertEqual(rep["empty_ratio"], 1.0)


class TurnExitTests(unittest.TestCase):
    def _transcript(self, d, user, assistant):
        p = Path(d) / "t.jsonl"
        lines = [{"type": "user", "timestamp": "2026-09-05T00:00:00Z", "message": {"role": "user", "content": user}},
                 {"type": "assistant", "timestamp": "2026-09-05T00:00:05Z", "message": {"role": "assistant", "content": [{"type": "text", "text": assistant}]}}]
        p.write_text("\n".join(json.dumps(l) for l in lines) + "\n"); return str(p)

    def test_promise_without_item_blocks_once_then_allows(self):
        d, env = fresh_env()
        tp = self._transcript(d, "fix it", "Sure. I will refactor the parser later tonight.")
        r = hook("turn_exit.py", {"transcript_path": tp, "stop_hook_active": False}, env)
        self.assertEqual(r.returncode, 2); self.assertIn("promise", r.stderr.lower())
        r = hook("turn_exit.py", {"transcript_path": tp, "stop_hook_active": True}, env)   # harness loop guard
        self.assertEqual(r.returncode, 0)

    def test_promise_with_a_new_item_passes(self):
        d, env = fresh_env()
        tp = self._transcript(d, "fix it", "I will refactor the parser tonight. [pending:refactor-parser]")
        run([Z, "open", "refactor-parser", "refactor the parser"], env)
        r = hook("turn_exit.py", {"transcript_path": tp, "stop_hook_active": False}, env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_completion_claim_without_receipt_warns_not_blocks(self):
        d, env = fresh_env()
        tp = self._transcript(d, "status?", "Done — the migration is completed and pushed.")
        r = hook("turn_exit.py", {"transcript_path": tp, "stop_hook_active": False}, env)
        self.assertEqual(r.returncode, 0)
        dec = (Path(d) / "state" / "gate_decisions.jsonl").read_text()
        self.assertIn("warn", dec); self.assertIn("receipt", dec)

    def test_locked_item_forces_dual_exit(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "1"
        run([Z, "open", "L1", "locked work"], env)
        run([P, "tick"], env)                                        # K=1: locks L1 immediately
        tp = self._transcript(d, "go", "All green, standing by.")
        r = hook("turn_exit.py", {"transcript_path": tp, "stop_hook_active": False}, env)
        self.assertEqual(r.returncode, 2); self.assertIn("L1", r.stderr)
        run([Z, "block", "L1", "--on", "needs the operator's password policy, asked 2026-09-05"], env)
        r = hook("turn_exit.py", {"transcript_path": tp, "stop_hook_active": False}, env)
        self.assertEqual(r.returncode, 0, r.stderr)


class WakeTests(unittest.TestCase):
    def test_fallback_wakes_with_reason(self):
        d, env = fresh_env()
        r = run([W, "wait", "--fallback", "1"], env)
        self.assertEqual(r.returncode, 0); self.assertIn("fallback", r.stdout)

    def test_wake_file_wakes_immediately(self):
        d, env = fresh_env()
        (Path(d) / "wake").write_text("now")
        t = time.time(); r = run([W, "wait", "--fallback", "30"], env)
        self.assertLess(time.time() - t, 5); self.assertIn("event:wake", r.stdout)


class TickIntegration(unittest.TestCase):
    def test_three_quiet_ticks_with_work_go_red_and_lock(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "3"; env["HEARTBEAT_SERVICE_FILTER"] = "^com\\.example\\.nothing$"
        run([Z, "open", "i1", "integration item"], env)
        import subprocess
        rcs = [subprocess.run(["bash", str(T)], capture_output=True, text=True, env=env).returncode for _ in range(3)]
        self.assertEqual(rcs[-1], 1)
        acts = [r["state"]["state"]["current_action"] for r in rounds(d)]
        self.assertTrue(any("IDLE_SPIN" in a for a in acts), acts)
        self.assertTrue(any("next:i1" in a for a in acts), acts)

    def test_empty_queue_tick_is_silent(self):
        d, env = fresh_env(); env["HEARTBEAT_IDLE_K"] = "1"; env["HEARTBEAT_SERVICE_FILTER"] = "^com\\.example\\.nothing$"
        import subprocess
        r = subprocess.run(["bash", str(T)], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "", r.stdout)      # green is silent
        self.assertIn("exit:noop", rounds(d)[-1]["state"]["state"]["current_action"])


if __name__ == "__main__":
    unittest.main()
