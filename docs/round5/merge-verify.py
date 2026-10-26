"""One-off: merge the resumed workflow's verification results into the raw
inventory JSON. Run from the repo root, then delete or keep as historical tool."""
import json
import os
import sys
from collections import Counter

src = sys.argv[1] if len(sys.argv) > 1 else (
    r"C:\Users\jlc\AppData\Local\Temp\claude\C--Users-jlc\f69eb284-3086-4e65-899c-ab21eeab0e91\tasks\w2xslcz09.output")
raw = open(src, encoding="utf-8", errors="replace").read()
wrapper = json.loads(raw)
data = wrapper["result"]

ver = data.get("verifications", [])
inv = data.get("inventory", [])
counts = data.get("counts", {})
print("scopes:", len(inv), "| verifications:", len(ver))
print("counts:", counts)
print("verdicts:", Counter(v["verdict"] for v in ver))
print("corrected:", Counter(v["corrected_status"] for v in ver if v["verdict"] != "CONFIRMED"))

out = os.path.join("docs", "round5", "a-inventory-raw.json")
os.makedirs("docs/round5", exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("saved:", out)
