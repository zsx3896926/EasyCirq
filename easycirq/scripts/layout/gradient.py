"""Gradient escalation: start fully soft, then hard-lock only the worst offenders,
a couple at a time, and keep the Pareto-best result.

Rationale (measured): soft spacing leaves 26 clearance violations; hard-locking all
10 conflicting nets drops clearance to 5 but loses 20 legs. Escalating in small
steps lets the negotiator reroute around each newly locked net before the next lock.
"""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("ec", HERE.parent / "ec_layout.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

board = ec.Board(json.load(open(r"retrocam-02/pcb/dump2.json", encoding="utf-8")))
ec.apply_placement(board, json.load(open(r"retrocam-02/pcb/offline/ec-placed.json", encoding="utf-8")))

hard = set()
rows = []
for step in range(6):
    (unr, cong), routed, fails = ec.route(board, iters=15, layers=4, hard_nets=hard or None)
    plan = ec.plan_from(board, routed)
    clear = ec.clearance_violations(board, plan)
    unconn = len(ec.connectivity_from_plan(board, plan))
    vias = len(plan["vias"])
    rows.append({"step": step, "hard": sorted(hard), "clearance": clear,
                 "unrouted": unr, "unconnected": unconn, "congestion": ec.congestion_from_plan(board, plan),
                 "vias": vias})
    print(f"step {step}: hard={sorted(hard)} clearance={clear} unrouted={unr} unconn={unconn} vias={vias}", flush=True)
    Path(r"retrocam-02/pcb/offline/ec-grad-%d.json" % step).write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    if unr == 0 and clear <= 5 and unconn <= 5:
        break
    pairs = ec.clearance_pairs(board, plan)
    counts = {}
    for a, b in pairs:
        for n in (a, b):
            if n != "GND":
                counts[n] = counts.get(n, 0) + 1
    add = [n for n, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if n not in hard][:2]
    if not add:
        break
    hard |= set(add)

best = min(rows, key=lambda r: (r["unrouted"] * 10 + r["unconnected"] * 5 + r["clearance"], r["vias"]))
Path(r"retrocam-02/pcb/offline/ec-grad-summary.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
print("BEST:", json.dumps(best))
