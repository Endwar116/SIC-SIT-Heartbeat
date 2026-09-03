import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

def fresh_env():
    d = tempfile.mkdtemp(prefix="sic-test-")
    env = dict(os.environ, HEARTBEAT_HOME=d, HEARTBEAT_AGENT="test-agent", HEARTBEAT_MODEL="test-model")
    return d, env

def run(args, env, stdin=None, cwd=None):
    return subprocess.run([PY] + [str(a) for a in args], input=stdin, capture_output=True, text=True, env=env, cwd=cwd or str(ROOT))

def hook(gate, payload, env):
    return subprocess.run([PY, str(ROOT / "gates" / gate)], input=json.dumps(payload), capture_output=True, text=True, env=env)
