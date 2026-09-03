import json, unittest
from pathlib import Path
from _util import ROOT, fresh_env, run

def derive(env, ctx, action):
    r = run([ROOT / "ledger/derive.py", "--context", ctx, "--action", action], env)
    assert r.returncode == 0, r.stderr
    return r.stdout

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.home, self.env = fresh_env()

    def test_append_three_and_verify(self):
        for i in range(3):
            r = run([ROOT / "ledger/ledger.py", "append", "-"], self.env, stdin=derive(self.env, f"c{i}", f"a{i}"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("⚓ R", r.stdout)
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env)
        self.assertEqual(v.returncode, 0); self.assertIn("3 rounds", v.stdout)
        rounds = [json.loads(l) for l in (Path(self.home) / "ledger/rounds.jsonl").read_text().splitlines()]
        self.assertEqual([w["state"]["round"] for w in rounds], [1, 2, 3])
        self.assertEqual(rounds[1]["prev_hash"], rounds[0]["hash"])
        self.assertEqual(rounds[2]["state"]["relation"]["upstream"], rounds[1]["hash"][:16])

    def test_tamper_middle_breaks_chain(self):
        for i in range(3):
            run([ROOT / "ledger/ledger.py", "append", "-"], self.env, stdin=derive(self.env, "c", f"a{i}"))
        p = Path(self.home) / "ledger/rounds.jsonl"
        lines = p.read_text().splitlines()
        w = json.loads(lines[1]); w["state"]["state"]["current_action"] = "EDITED"
        lines[1] = json.dumps(w, ensure_ascii=False); p.write_text("\n".join(lines) + "\n")
        v = run([ROOT / "ledger/ledger.py", "verify"], self.env)
        self.assertEqual(v.returncode, 1); self.assertIn("BROKEN", v.stdout); self.assertIn("seq 2", v.stdout)

    def test_self_close_is_flagged_not_blocked(self):
        st = json.loads(derive(self.env, "c", "a")); st["task"]["status"] = "completed"
        r = run([ROOT / "ledger/ledger.py", "append", "-"], self.env, stdin=json.dumps(st))
        self.assertEqual(r.returncode, 0); self.assertIn("GOVERNANCE FLAG", r.stderr)
        w = json.loads((Path(self.home) / "ledger/rounds.jsonl").read_text().splitlines()[0])
        self.assertEqual(w["governance_flag"], "AI_SELF_CLOSED")

    def test_missing_required_key_rejected(self):
        st = json.loads(derive(self.env, "c", "a")); del st["intent"]
        r = run([ROOT / "ledger/ledger.py", "append", "-"], self.env, stdin=json.dumps(st))
        self.assertEqual(r.returncode, 2); self.assertIn("intent", r.stderr)

if __name__ == "__main__":
    unittest.main()
