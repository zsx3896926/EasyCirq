"""Debug why bundle fan-out places only 1 of 8 members."""
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("ec", r"hds-verifier/tools/layout/ec_layout.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

board = ec.Board(json.load(open(r"retrocam-02/pcb/dump2.json", encoding="utf-8")))
ec.apply_placement(board, json.load(open(r"retrocam-02/pcb/offline/ec-placed.json", encoding="utf-8")))
board.pad_blocked()

for prefix, layer in (("CAM_D", 3), ("LCD_", 4), ("SD_", 4)):
    nets = sorted(n for n in board.nets if n.startswith(prefix))
    pairs = [(n, board.nets[n][0], board.nets[n][1]) for n in nets if len(board.nets[n]) >= 2]
    print(f"\n{prefix}: {len(pairs)} nets")
    for n, a, b in pairs[:3]:
        print(f"   {n}: {a['des']}.{a['pad']} ({a['x']:.0f},{a['y']:.0f}) -> "
              f"{b['des']}.{b['pad']} ({b['x']:.0f},{b['y']:.0f})")
    if len(pairs) >= 2:
        ys = sorted(p[1]["y"] for p in pairs)
        print(f"   source y spread: {ys[0]:.0f}..{ys[-1]:.0f}")
        esc = ec.pad_escape_dirs(board)
        print("   escapes:", {p[0]: esc.get((p[1]["des"], p[1]["pad"])) for p in pairs[:4]})
