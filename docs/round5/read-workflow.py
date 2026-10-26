"""One-off: summarize a completed workflow output file (verdicts + refutations)."""
import json
import sys
from collections import Counter

raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
d = json.loads(raw)
res = d.get("result", d)
ver = res.get("verifications", [])
print("counts:", res.get("counts"))
print("verdicts:", Counter(v.get("verdict") for v in ver))
for v in ver:
    if v.get("verdict") != "CONFIRMED":
        print("---")
        print("claim:", v.get("claim_id"))
        print("verdict:", v.get("verdict"))
        print("reason:", (v.get("reason") or "")[:500])
