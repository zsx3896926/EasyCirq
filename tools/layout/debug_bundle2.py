"""Diagnose exactly which cells/nets block the 2nd and 3rd bundle member."""
import importlib.util
import json

spec = importlib.util.spec_from_file_location("ec", r"hds-verifier/tools/layout/ec_layout.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

board = ec.Board(json.load(open(r"retrocam-02/pcb/dump2.json", encoding="utf-8")))
ec.apply_placement(board, json.load(open(r"retrocam-02/pcb/offline/ec-placed.json", encoding="utf-8")))
board.pad_blocked()

prefix, layer, pitch = "CAM_D", 3, 25.0
nets = sorted(n for n in board.nets if n.startswith(prefix))
pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
pairs.sort(key=lambda t: t[1]["x"])
print("members:", [(p[0], round(p[1]["x"]), round(p[1]["y"]), round(p[2]["x"]), round(p[2]["y"])) for p in pairs[:4]])

occ = {}
placed = 0
trunk = min(p[2]["x"] for p in pairs) - 40.0
src_ref = min(p[1]["y"] for p in pairs)
for i, (net, a, b) in enumerate(pairs):
    lane = src_ref + (i + 1) * pitch
    drop_x = trunk - (i + 1) * pitch
    pts = [(a["x"], a["y"]), (a["x"], lane), (trunk, lane),
           (drop_x, lane), (drop_x, b["y"]), (b["x"], b["y"])]
    clash_at = None
    for p0, p1 in zip(pts, pts[1:]):
        if abs(p0[0] - p1[0]) < 1e-9 and abs(p0[1] - p1[1]) < 1e-9:
            continue
        seg = {"net": net, "layer": layer, "width": 7.0,
               "x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
        for cell in ec._segment_cells(board, seg, halo=0):
            owner = occ.get(cell)
            if owner and owner != net:
                clash_at = (cell, owner, p0, p1)
                break
        if clash_at:
            break
    if clash_at:
        cell, owner, p0, p1 = clash_at
        print(f"  {net}: CLASH at cell {cell} owned by {owner}; segment {p0}->{p1}")
    else:
        for p0, p1 in zip(pts, pts[1:]):
            seg = {"net": net, "layer": layer, "width": 7.0,
                   "x1": p0[0], "y1": p0[1], "x2": p1[0], "y2": p1[1]}
            for cell in ec._segment_cells(board, seg, halo=1):
                occ[cell] = net
        placed += 1
        print(f"  {net}: placed (lane={lane:.0f}, drop_x={drop_x:.0f})")
print("placed", placed, "/", len(pairs))
