"""Replay bundle_route_channel for one group and print WHY members are rejected."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("ec", HERE.parent / "ec_layout.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

prefix = sys.argv[1] if len(sys.argv) > 1 else "CAM_D"
lane = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
layer = int(sys.argv[3]) if len(sys.argv) > 3 else 3

board = ec.Board(json.load(open(r"retrocam-02/pcb/dump2.json", encoding="utf-8")))
ec.apply_placement(board, json.load(open(r"retrocam-02/pcb/offline/ec-placed.json", encoding="utf-8")))
board.pad_blocked()

pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in sorted(board.nets)
         if n.startswith(prefix) and len(board.nets[n]) >= 2]
pairs.sort(key=lambda t: t[1]["x"])
by_dst = sorted(pairs, key=lambda t: t[2]["y"])
dst_ys = [p[2]["y"] for p in by_dst]
dst_pitch = lane
if len(dst_ys) >= 2:
    diffs = [abs(dst_ys[i + 1] - dst_ys[i]) for i in range(len(dst_ys) - 1) if abs(dst_ys[i + 1] - dst_ys[i]) > 0]
    if diffs:
        dst_pitch = min(diffs)
band = max(max(dst_ys), pairs[0][1]["y"]) + 3 * dst_pitch
lane_of = {p[0]: band + k * dst_pitch for k, p in enumerate(by_dst)}
print(f"{prefix}: {len(pairs)} members, dst_pitch={dst_pitch:.0f}, band={band:.0f}")

occ = {}
for net, a, b in pairs:
    lane_y = lane_of[net]
    p1 = (a["x"] + (lane_y - a["y"]), lane_y)
    p2 = (b["x"] + (lane_y - b["y"]), lane_y)
    pts = [(a["x"], a["y"]), p1, p2, (b["x"], b["y"])]
    clash = None
    for p0, pn in zip(pts, pts[1:]):
        if abs(p0[0] - pn[0]) < 1e-9 and abs(p0[1] - pn[1]) < 1e-9:
            continue
        seg = {"net": net, "layer": layer, "width": 7.0,
               "x1": p0[0], "y1": p0[1], "x2": pn[0], "y2": pn[1]}
        for cell in ec._segment_cells(board, seg, halo=0):
            owner = occ.get(cell)
            if owner and owner != net:
                clash = (cell, owner, p0, pn)
                break
        if clash:
            break
    if clash:
        cell, owner, p0, pn = clash
        print(f"  {net:8s} CLASH cell={cell} owner={owner} seg {tuple(round(v) for v in p0)}->{tuple(round(v) for v in pn)}")
    else:
        for p0, pn in zip(pts, pts[1:]):
            seg = {"net": net, "layer": layer, "width": 7.0,
                   "x1": p0[0], "y1": p0[1], "x2": pn[0], "y2": pn[1]}
            for cell in ec._segment_cells(board, seg, halo=1):
                occ[cell] = net
        print(f"  {net:8s} placed lane_y={lane_y:.0f}")
