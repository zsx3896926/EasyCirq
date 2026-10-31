"""Bus pin-order planarity diagnostic + orientation advice.

A planar equal-length bundle needs source order and destination order to be
monotonic in the same direction (|rho| ~ 1). This script:

  1. reports rho per bus group for the current placement;
  2. tries every 90-degree rotation / mirror of the MCU and reports the best
     orientation, i.e. what an agent should do to the part to make the bus planar.

Usage: python check_bus_order.py dump.json [placed.json] [--mcu U5]
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("ec_layout", _HERE.parent / "ec_layout.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

GROUPS = ("CAM_D", "LCD_", "SD_")


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0] * len(values)
    for rank, i in enumerate(order):
        r[i] = rank
    return r


def spearman(a, b):
    if len(a) < 2:
        return 0.0
    ra, rb = ranks(a), ranks(b)
    m = (len(a) - 1) / 2
    num = sum((ra[i] - m) * (rb[i] - m) for i in range(len(a)))
    den = math.sqrt(sum((x - m) ** 2 for x in ra) * sum((x - m) ** 2 for x in rb))
    return num / den if den else 0.0


def group_pairs(board, prefix):
    nets = sorted(n for n in board.nets if n.startswith(prefix) and len(board.nets[n]) >= 2)
    return [(n, board.nets[n][0], board.nets[n][1]) for n in nets]


def transform_component(board, des, rot, mirror, mirror_axis="x"):
    """Return {pad_key: (x, y)} for the component under a rotation/mirror about its
    own centre, WITHOUT mutating the board. mirror_axis="y" flips the pin order
    along the pin row (an x-mirror leaves the vertical order untouched, which is why
    the earlier "best orientation" printout was meaningless)."""
    c = board.comps[des]
    out = {}
    for p in c["pads"]:
        dx, dy = p["x"] - c["x"], p["y"] - c["y"]
        if mirror:
            if mirror_axis == "y":
                dy = -dy
            else:
                dx = -dx
        a = math.radians(rot)
        rx = dx * math.cos(a) - dy * math.sin(a)
        ry = dx * math.sin(a) + dy * math.cos(a)
        out[(des, p["pad"])] = (c["x"] + rx, c["y"] + ry)
    return out


def rho_for(board, prefix, override=None):
    pairs = group_pairs(board, prefix)
    if len(pairs) < 2:
        return None
    sx, dy = [], []
    for _n, a, b in pairs:
        sx.append(a["x"])
        key = (b["des"], b["pad"])
        dy.append(override[key][1] if override and key in override else b["y"])
    return spearman(sx, dy)


def main():
    dump = sys.argv[1]
    placed = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    mcu = "U5"
    if "--mcu" in sys.argv:
        mcu = sys.argv[sys.argv.index("--mcu") + 1]
    board = ec.Board(json.load(open(dump, encoding="utf-8")))
    if placed:
        ec.apply_placement(board, json.load(open(placed, encoding="utf-8")))

    print("current placement:")
    for g in GROUPS:
        r = rho_for(board, g)
        print(f"  {g:6s} rho = {r:+.2f}" if r is not None else f"  {g:6s} n/a")

    print(f"\nbest orientation of {mcu} per group:")
    for g in GROUPS:
        best = None
        for rot in (0, 90, 180, 270):
            for mir, axis in ((False, "x"), (True, "x"), (True, "y")):
                ov = transform_component(board, mcu, rot, mir, axis)
                r = rho_for(board, g, ov)
                if r is None:
                    continue
                if best is None or abs(r) > best[0]:
                    best = (abs(r), rot, mir, axis, r)
        if best:
            _s, brot, bmir, baxis, br = best
            print(f"  {g:6s} best: rotate {brot:3d}deg mirror={bmir}(axis {baxis}) -> rho {br:+.2f}")


if __name__ == "__main__":
    main()
