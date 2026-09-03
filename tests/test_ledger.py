import json, subprocess, sys, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from _util import ROOT, fresh_env, run

def derive(env, ctx="c", action="a"):
    r = run([ROOT / "ledger/derive.py", "--context", ctx, "--action", action], env)
    assert r.returncode == 0, r.stderr
    return r.stdout

def append(env, state_json, *extra):
    return run([ROOT / "ledger/ledger.py", "append", "-", *extra], env, stdin=state_json)

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.home, self.env = fresh_env(); self.rounds = Path(self.home) / "ledger/rounds.jsonl"

    def test_append_three_and_verify(self):
        for i in range(3):
            r = append(self.env, derive(self.env, f"c{i}", f"a{i}")); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("⚓ R", r.stdout)
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env); self.assertEqual(v.returncode, 0, v.stdout); self.assertIn("3 rounds", v.stdout)
        rows = [json.loads(l) for l in self.rounds.read_text().splitlines()]
        self.assertEqual([w["state"]["round"] for w in rows], [1, 2, 3]); self.assertEqual(rows[1]["prev_hash"], rows[0]["hash"])
        self.assertIsNone(rows[0]["state"]["relation"]["upstream"]); self.assertEqual(rows[2]["state"]["relation"]["upstream"], rows[1]["hash"][:16])
        self.assertEqual(rows[0]["ledger_version"], 2)

    def _three(self):
        for i in range(3): append(self.env, derive(self.env, "c", f"a{i}"))
        return self.rounds.read_text().splitlines()

    def _rewrite(self, lines):
        self.rounds.write_text("\n".join(lines) + "\n")

    def test_tamper_state_breaks_chain(self):
        lines = self._three(); w = json.loads(lines[1]); w["state"]["state"]["current_action"] = "EDITED"; lines[1] = json.dumps(w, ensure_ascii=False); self._rewrite(lines)
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env); self.assertEqual(v.returncode, 1); self.assertIn("seq 2", v.stdout)

    def test_tamper_seq_or_timestamp_detected(self):
        for field, val in (("seq", 999), ("logged_at", "1999-01-01T00:00:00+00:00")):
            self.setUp(); lines = self._three(); w = json.loads(lines[1]); w[field] = val; lines[1] = json.dumps(w, ensure_ascii=False); self._rewrite(lines)
            v = run([ROOT / "ledger/ledger.py", "verify"], self.env); self.assertEqual(v.returncode, 1, field)

    def test_deleted_trailing_line_detected_via_state_current(self):
        lines = self._three(); self._rewrite(lines[:2])
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env); self.assertEqual(v.returncode, 1); self.assertIn("STATE_CURRENT", v.stdout)

    def test_continuity_enforced_and_overridable(self):
        append(self.env, derive(self.env)); st = json.loads(derive(self.env)); st["round"] = 42
        r = append(self.env, json.dumps(st)); self.assertEqual(r.returncode, 2); self.assertIn("continuity", r.stderr)
        r2 = append(self.env, json.dumps(st), "--allow-discontinuity", "migrated from old ledger"); self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("discontinuity", self.rounds.read_text().splitlines()[-1])
        self.assertEqual(run([ROOT / "ledger/ledger.py", "verify"], self.env).returncode, 0)

    def test_identity_change_blocked(self):
        append(self.env, derive(self.env)); st = json.loads(derive(self.env)); st["entity"]["name"] = "impostor"
        r = append(self.env, json.dumps(st)); self.assertEqual(r.returncode, 2); self.assertIn("entity.name", r.stderr)

    def _parallel(self, extra=""):
        def one(i):
            return subprocess.run(f"{sys.executable} {ROOT}/ledger/derive.py --context c --action a{i} | {sys.executable} {ROOT}/ledger/ledger.py append - {extra}",
                                  shell=True, capture_output=True, text=True, env=self.env).returncode
        with ThreadPoolExecutor(8) as ex: return list(ex.map(one, range(8)))

    def test_concurrent_appends_with_auto_round_keep_chain_intact(self):
        codes = self._parallel("--auto-round")
        self.assertTrue(all(c == 0 for c in codes), codes)
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env); self.assertEqual(v.returncode, 0, v.stdout); self.assertIn("8 rounds", v.stdout)

    def test_concurrent_appends_without_auto_round_fail_closed_not_corrupt(self):
        codes = self._parallel()
        self.assertTrue(all(c in (0, 2) for c in codes), codes)          # stale rounds are refused, never written
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env); self.assertEqual(v.returncode, 0, v.stdout)
        self.assertEqual(self.rounds.read_text().count("\n"), codes.count(0))

    def test_torn_tail_detected_and_repairable(self):
        self._three(); pending = derive(self.env)
        self.rounds.write_bytes(self.rounds.read_bytes() + b'{"ledger_version": 2, "seq": 4, "logged')
        self.assertEqual(run([ROOT / "ledger/ledger.py", "verify"], self.env).returncode, 1)
        self.assertEqual(append(self.env, pending).returncode, 1)                      # refuses to append onto a torn file
        self.assertEqual(run([ROOT / "ledger/derive.py", "--context", "c", "--action", "a"], self.env).returncode, 1)  # derive also refuses, cleanly
        rep = run([ROOT / "ledger/ledger.py", "repair", "--torn-tail"], self.env); self.assertEqual(rep.returncode, 0, rep.stdout)
        self.assertTrue(list((Path(self.home) / "ledger/torn").iterdir()))
        self.assertEqual(append(self.env, derive(self.env)).returncode, 0)
        self.assertEqual(run([ROOT / "ledger/ledger.py", "verify"], self.env).returncode, 0)

    def test_self_close_is_flagged_not_blocked(self):
        st = json.loads(derive(self.env)); st["task"]["status"] = "completed"
        r = append(self.env, json.dumps(st)); self.assertEqual(r.returncode, 0); self.assertIn("GOVERNANCE FLAG", r.stderr)
        self.assertEqual(json.loads(self.rounds.read_text().splitlines()[0])["governance_flag"], "AI_SELF_CLOSED")

    def test_bad_inputs_exit_2_without_traceback(self):
        base = json.loads(derive(self.env))
        cases = []
        d = dict(base); del d["intent"]; cases.append(d)
        d = json.loads(json.dumps(base)); d["round"] = True; cases.append(d)
        d = json.loads(json.dumps(base)); d["task"] = "str"; cases.append(d)
        d = json.loads(json.dumps(base)); d["state"] = "str"; cases.append(d)
        for c in cases:
            r = append(self.env, json.dumps(c)); self.assertEqual(r.returncode, 2, c); self.assertNotIn("Traceback", r.stderr)
        r = append(self.env, json.dumps(base).replace('"round": 1', '"round": 1, "x": NaN')); self.assertEqual(r.returncode, 2)

    def test_v1_wrapper_still_verifies(self):
        import hashlib
        st = json.loads(derive(self.env)); can = json.dumps(st, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        h = hashlib.sha256(("0" * 64 + can).encode()).hexdigest()
        self.rounds.parent.mkdir(parents=True, exist_ok=True)
        self.rounds.write_text(json.dumps({"seq": 1, "logged_at": "x", "hash": h, "prev_hash": "0" * 64, "state": st}) + "\n")
        (Path(self.home) / "ledger/STATE_CURRENT.json").write_text(json.dumps({"seq": 1, "hash": h, "state": st}))
        self.assertEqual(run([ROOT / "ledger/ledger.py", "verify"], self.env).returncode, 0)

if __name__ == "__main__":
    unittest.main()
