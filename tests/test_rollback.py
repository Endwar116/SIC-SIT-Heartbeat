import unittest
from pathlib import Path
from _util import ROOT, fresh_env, run

class Tombstone(unittest.TestCase):
    def setUp(self): self.home, self.env = fresh_env()
    def test_trash_verify_restore(self):
        src = Path(self.home) / "work/thing"; src.mkdir(parents=True); (src / "a.txt").write_text("A"); (src / "sub").mkdir(); (src / "sub/b.txt").write_text("B")
        t = run([ROOT / "rollback/tombstone.py", "trash", src, "--why", "test cleanup"], self.env)
        self.assertEqual(t.returncode, 0, t.stderr); self.assertFalse(src.exists())
        entry = next(p for p in (Path(self.home) / "trash").iterdir() if (p / "TOMBSTONE.md").exists())
        tomb = (entry / "TOMBSTONE.md").read_text()
        self.assertIn("test cleanup", tomb); self.assertIn("restore", tomb); self.assertTrue((entry / "MANIFEST.sha256.json").exists())
        self.assertEqual(run([ROOT / "rollback/tombstone.py", "verify", entry], self.env).returncode, 0)
        r = run([ROOT / "rollback/tombstone.py", "restore", entry], self.env)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual((src / "sub/b.txt").read_text(), "B"); self.assertTrue((entry / "RESTORED.md").exists())
    def test_restore_refuses_to_overwrite(self):
        src = Path(self.home) / "f.txt"; src.write_text("x")
        run([ROOT / "rollback/tombstone.py", "trash", src, "--why", "w"], self.env)
        src.write_text("new")
        entry = next(p for p in (Path(self.home) / "trash").iterdir())
        self.assertNotEqual(run([ROOT / "rollback/tombstone.py", "restore", entry], self.env).returncode, 0)

if __name__ == "__main__":
    unittest.main()
