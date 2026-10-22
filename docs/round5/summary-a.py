"""One-off: print a compact verified-status summary of package A inventory.
Run: python docs/round5/summary-a.py > docs/round5/a-summary.txt"""
import json

data = json.load(open("docs/round5/a-inventory-raw.json", encoding="utf-8"))
vermap = {}
for v in data["verifications"]:
    if v["verdict"] == "REFUTED":
        vermap[v["claim_id"]] = ("REFUTED->" + v["corrected_status"], v["reason"][:160])
print("verifications: %d confirmed, %d refuted" % (
    sum(1 for v in data["verifications"] if v["verdict"] == "CONFIRMED"),
    sum(1 for v in data["verifications"] if v["verdict"] == "REFUTED")))
print()
for i, r in enumerate(data["inventory"]):
    print("--- scope %d: %s" % (i, r["scope"][:50]))
    for f in r["findings"]:
        tag = vermap.get(f["id"])
        extra = " [" + tag[0] + "]" if tag else ""
        print("  %-8s %-24s %s%s" % (f["status"], f["id"], f["title"][:70], extra))
    print()
