#!/usr/bin/env python3
"""prereg_seal.py — seal a pre-registration so prereg_gate.py will accept it.

Two seal formats, both borrowed from practice (not invented here):
  machine seal (prereg.json): {"run_id","preregistration_hash","sealed_at","immutable":true,"payload":{...}}
  sidecar (<doc>.sha256):     "<sha256>  <filename>  frozen_at=<ISO>"

Payload discipline baked into the template (each line is a lesson someone paid for):
  primary_metric      exactly ONE; everything else is exploratory
  falsification       written before running; commit to publishing an unfavourable pilot direction
  analysis_plan       state the denominator rule: who is excluded from rates and why
  confounds           prefer elimination by construction over statistical adjustment
  stopping_rule       when you stop and publish as-is
  downgrade_clause    the conditions under which you must demote your own conclusion
  declared_limitations written before results exist

Commands:  template [--out f]  |  new payload.json [--out dir]  |  sidecar doc.md  |  verify <prereg.json|doc.md>
"""
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

TEMPLATE = {
    "suite_id": "<EXPERIMENT-ID>",
    "arms": ["<control>", "<treatment>", "<negative control: looks the same, content scrambled>"],
    "n_per_arm": 0,
    "seed": 42,
    "hypothesis": "<directional, written before running>",
    "primary_metric": "<exactly one>",
    "falsification": "<PRIMARY: what result refutes this. If a pilot already points the other way, commit here to publish it.>",
    "analysis_plan": "<test + multiple-comparison correction + CI; denominator rule: excluded who, why>",
    "confounds": "<eliminated by construction how; else adjusted how>",
    "stopping_rule": "<when to stop and publish as-is>",
    "exclusion_rule": "<data exclusion rules, fixed now>",
    "declared_limitations": ["<written before results exist>"],
    "downgrade_clause": "<conditions under which I must demote my own conclusion>",
    "drafted_by": "<who> <date> - DRAFT, awaiting sign-off before external citation",
}


def canonical(o): return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
def sha(b): return hashlib.sha256(b if isinstance(b, bytes) else canonical(b).encode()).hexdigest()


def cmd_new(path, out_dir):
    payload = json.load(open(path, encoding="utf-8"))
    missing = [k for k in ("suite_id", "primary_metric", "falsification", "analysis_plan", "n_per_arm", "drafted_by")
               if not payload.get(k)]
    if missing:
        sys.exit(f"❌ payload missing required fields: {missing}")
    if isinstance(payload.get("primary_metric"), list) and len(payload["primary_metric"]) > 1:
        sys.exit("❌ primary_metric must be exactly one (others are exploratory)")
    h = sha(payload)
    doc = {"run_id": f"{payload['suite_id'].lower()}-{date.today().isoformat()}-{h[:8]}",
           "preregistration_hash": "sha256:" + h,
           "sealed_at": datetime.now(timezone.utc).isoformat(), "immutable": True, "payload": payload}
    out_dir = out_dir or os.path.dirname(os.path.abspath(path))
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, "prereg.json")
    if os.path.exists(dest):
        sys.exit(f"❌ {dest} exists — a seal is never overwritten. Make a new directory / version.")
    json.dump(doc, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ sealed {dest}\n   run_id={doc['run_id']}\n   hash={doc['preregistration_hash'][:24]}…\n"
          f"   -> reference this path from your experiment script to pass prereg_gate")


def cmd_sidecar(path):
    h = sha(open(path, "rb").read())
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    open(path + ".sha256", "w", encoding="utf-8").write(f"{h}  {os.path.basename(path)}  frozen_at={ts}\n")
    print(f"✅ sidecar written {path}.sha256  ({h[:16]}…)")


def cmd_verify(path):
    if path.endswith(".json"):
        doc = json.load(open(path, encoding="utf-8"))
        want = doc.get("preregistration_hash", "").replace("sha256:", "")
        got = sha(doc.get("payload") or {})
        ok = want == got
        print("✅ seal intact" if ok else "❌ seal BROKEN (payload modified)")
        return 0 if ok else 1
    side = path + ".sha256"
    if not os.path.exists(side):
        print(f"❌ no sidecar {side}"); return 1
    want = open(side, encoding="utf-8").read().split()[0]
    ok = want == sha(open(path, "rb").read())
    print("✅ document unchanged" if ok else "❌ document modified since freeze")
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    out = a[a.index("--out") + 1] if "--out" in a else None
    if a[0] == "template":
        dest = out or "prereg_payload.json"
        json.dump(TEMPLATE, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"✅ template written {dest} — fill it, then: prereg_seal.py new {dest}"); return
    if len(a) < 2:
        print(__doc__); sys.exit(2)
    if a[0] == "new": cmd_new(a[1], out)
    elif a[0] == "sidecar": cmd_sidecar(a[1])
    elif a[0] == "verify": sys.exit(cmd_verify(a[1]))
    else: print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
