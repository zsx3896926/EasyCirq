"""One-off: inspect the ONENETNAME-flagged wires in the frozen F1 snapshot."""
import json
import sys

snap = json.load(open("docs/evidence/f1-b-2026-10-22/snapshot-before.json", encoding="utf-8"))
snap = snap.get("snapshot", snap)

flagged = {"49fae01dc70fc99a", "257ae6235df06193"}

wires = snap.get("wires") or []
flags = snap.get("net_flags") or []
ports = snap.get("net_ports") or []

print("== flagged wires")
for w in wires:
    if w.get("primitive_id") in flagged:
        print(json.dumps(w, ensure_ascii=False, indent=1))

print("== all netflags on/near GND (coords in wire bbox)")
near = lambda x, y, w: abs(x - w["x"]) < 300 and abs(y - w["y"]) < 300
for w in wires:
    if w.get("primitive_id") in flagged:
        for f in flags:
            if near(f.get("x"), f.get("y"), w):
                print("  flag:", json.dumps(f, ensure_ascii=False)[:200])

print("== wire structure keys sample")
if wires:
    print(json.dumps(wires[0], ensure_ascii=False, indent=1)[:600])
