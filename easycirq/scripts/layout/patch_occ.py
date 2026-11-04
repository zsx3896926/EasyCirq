"""One-shot: make every bundle occupancy table keyed by (x, y, LAYER).

Cross-layer false conflicts were blocking bundles: a member on L4 was rejected
because a member on L3 owned the same (x, y) cell. The split function was fixed by
hand; this script applies the same key to the remaining functions.
"""
from pathlib import Path

p = Path(r"hds-verifier/tools/layout/ec_layout.py")
s = p.read_text(encoding="utf-8")
before = s

s = s.replace("                owner = occ.get(cell)", "                owner = occ.get((cell[0], cell[1], layer))")
s = s.replace("                occ[cell] = net", "                occ[(cell[0], cell[1], layer)] = net")
s = s.replace("                    owner = occ.get(cell)", "                    owner = occ.get((cell[0], cell[1], layer))")
s = s.replace("                    occ[cell] = net", "                    occ[(cell[0], cell[1], layer)] = net")

if s == before:
    print("no changes applied (patterns not found)")
else:
    p.write_text(s, encoding="utf-8")
    print("patched:", before.count("occ.get(cell)") + before.count("occ[cell] = net"), "sites")
