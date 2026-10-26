"""One-off: extract DRC / title block / NC related API type names from the
client's `doc api` dump."""
import json
import sys

raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
d = json.loads(raw, strict=False)
types = d["value"]["types"]
print("total types:", len(types))
for t in types:
    if not isinstance(t, dict):
        continue
    n = t.get("name", "")
    if any(k in n.lower() for k in ("drc", "titleblock", "title_block", "noconnect", "no_connect", "sch_")):
        print(n, "|", t.get("comment"))
