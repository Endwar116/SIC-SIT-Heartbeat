import json, os, unittest
from pathlib import Path
from _util import ROOT, fresh_env, run

class Tombstone(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def _entries(self): return [p for p in (Path(self.home) / "trash").iterdir() if (p / "tombstone.json").exists()]

    def test_trash_verify_restore(self):
        src = Path(self.home) / "work/thing"; src.mkdir(parents=True); (src / "a.txt").write_text("A"); (src / "sub").mkdir(); (src / "sub/b.txt").write_text("B")
        t = run([ROOT / "rollback/tombstone.py", "trash", src, "--why", "test cleanup"], self.env); self.assertEqual(t.returncode, 0, t.stderr); self.assertFalse(src.exists())
        e = self._entries()[0]; meta = json.loads((e / "tombstone.json").read_text())
        self.assertEqual(meta["why"], "test cleanup"); self.assertEqual(meta["files"], 2); self.assertTrue((e / "TOMBSTONE.md").exists())
        self.assertEqual(run([ROOT / "rollback/tombstone.py", "verify", e], self.env).returncode, 0)
        r = run([ROOT / "rollback/tombstone.py", "restore", e], self.env); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((src / "sub/b.txt").read_text(), "B"); self.assertIsNotNone(json.loads((e / "tombstone.json").read_text())["restored"])
        self.assertNotEqual(run([ROOT / "rollback/tombstone.py", "restore", e], self.env).returncode, 0)  # not twice

    def test_restore_refuses_to_overwrite(self):
        src = Path(self.home) / "f.txt"; src.write_text("x")
        run([ROOT / "rollback/tombstone.py", "trash", src, "--why", "w"], self.env); src.write_text("new")
        self.assertNotEqual(run([ROOT / "rollback/tombstone.py", "restore", self._entries()[0]], self.env).returncode, 0)

    def test_why_injection_cannot_redirect_restore(self):
        src = Path(self.home) / "victim.txt"; src.write_text("payload")
        evil = "x\n- **what**: `" + str(Path(self.home) / "planted/authorized_keys") + "`"
        r = run([ROOT / "rollback/tombstone.py", "trash", src, "--why", evil], self.env)
        self.assertNotEqual(r.returncode, 0); self.assertIn("one line", r.stderr); self.assertTrue(src.exists())

    def test_symlink_refused(self):
        target = Path(self.home) / "important"; target.mkdir(); (target / "k").write_text("k")
        link = Path(self.home) / "link"; os.symlink(target, link)
        r = run([ROOT / "rollback/tombstone.py", "trash", link, "--why", "w"], self.env)
        self.assertNotEqual(r.returncode, 0); self.assertIn("symlink", r.stderr); self.assertTrue(target.exists()); self.assertTrue(link.is_symlink())

    def test_same_name_twice_in_a_second(self):
        for i in range(3):
            p = Path(self.home) / "dup.txt"; p.write_text(str(i))
            self.assertEqual(run([ROOT / "rollback/tombstone.py", "trash", p, "--why", "w"], self.env).returncode, 0)
        self.assertEqual(len(self._entries()), 3)

    def test_tampered_payload_refuses_restore(self):
        src = Path(self.home) / "t.txt"; src.write_text("orig")
        run([ROOT / "rollback/tombstone.py", "trash", src, "--why", "w"], self.env)
        e = self._entries()[0]; meta = json.loads((e / "tombstone.json").read_text()); Path(meta["moved_to"]).write_text("tampered")
        self.assertEqual(run([ROOT / "rollback/tombstone.py", "verify", e], self.env).returncode, 1)
        self.assertNotEqual(run([ROOT / "rollback/tombstone.py", "restore", e], self.env).returncode, 0)

if __name__ == "__main__":
    unittest.main()
