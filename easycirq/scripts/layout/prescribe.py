#!/usr/bin/env python3
"""Apply the measured design prescription to a dump + placement, in ONE documented order.

Sections 98-111 measured that this combination is worth something, but §113 found that the historical
candidate files came from an ad-hoc application order that could not be reconstructed: a recipe written
from the prose produced a different pin assignment (24 pads differed).  This tool fixes that by being the
canonical definition: a fixed sequence with fixed arguments, applied to the ORIGINAL inputs every time, so
running it twice gives byte-identical output.

The sequence (and nothing else):

  1. pad shrink            U1 pads 20 mil tall, U4 40, L1 80              (§98)
  2. bus repin             rank-match both ends of every bus group        (§99)
  3. CAM block             CAM nets onto U5 pads 13..20                   (§108)
  4. SD block              SD nets onto U5 pads 23..26                    (§108)
  5. bus repin again       rank-match after the blocks
  6. LCD pairing reversal  swap U5 pads 31<->35 and 32<->34               (§110)
  7. placement             J3 x -50 mil, J4 +120/+100 mil                 (§109)

Every step is an explicit assignment derived from the ORIGINAL dump (never from a mutated one), which is
what makes it idempotent.  The output is a candidate for measurement, not a board change: the pads, the
pin map and the placement are all simulated.

Usage
-----
    python easycirq/scripts/layout/prescribe.py --dump dump2.json --place ec-placed.json --out-dir out/recipe
    # then, to measure it:
    python easycirq/scripts/layout/reproduce.py --dump out/recipe/dump.json --place out/recipe/place.json \
        --profile strict-via-thin --out-dir out/recipe/run
"""
import argparse
import copy
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import whatif  # noqa: E402

PAD_SHRINK = ["U1=20", "U4=40", "L1=80"]
PART = "U5"
CAM_PADS = ["13", "14", "15", "16", "17", "18", "19", "20"]
SD_PADS = ["23", "24", "25", "26"]
LCD_SWAPS = [("31", "35"), ("32", "34")]
MOVES = {"J3": (-50.0, 0.0), "J4": (120.0, 100.0)}


def pad_id(p):
    return p.get("padNumber") or p.get("pad")


def pads_of(dump, part):
    for c in (dump.get("result") or dump).get("components") or []:
        if c["designator"] == part:
            return c.get("pads") or []
    raise SystemExit("part %s not found in the dump" % part)


def assign_block(dump, group, ids, part=PART):
    """Put `group`'s nets on `ids`; the displaced nets take the group's old pads. A permutation."""
    pads = pads_of(dump, part)
    by_id = {pad_id(p): p for p in pads}
    group_pads = [p for p in pads if str(p.get("net") or "").startswith(group)]
    nets = sorted(p.get("net") for p in group_pads)
    targets = [by_id[i] for i in ids if i in by_id]
    if len(targets) != len(nets):
        raise SystemExit("%s: %d pads for %d nets" % (group, len(targets), len(nets)))
    displaced = [p.get("net") for p in targets if not str(p.get("net") or "").startswith(group)]
    moved_out = [p for p in group_pads if pad_id(p) not in ids]
    if len(displaced) != len(moved_out):
        raise SystemExit("%s: %d displaced vs %d freed - not a permutation"
                         % (group, len(displaced), len(moved_out)))
    for p, n in zip(targets, nets):
        p["net"] = n
    for p, n in zip(moved_out, displaced):
        p["net"] = n


def swap_nets(dump, a, b, part=PART):
    pads = {pad_id(p): p for p in pads_of(dump, part)}
    if a not in pads or b not in pads:
        raise SystemExit("swap needs pads %s/%s on %s" % (a, b, part))
    pads[a]["net"], pads[b]["net"] = pads[b]["net"], pads[a]["net"]


def build(dump, place, cam_pads=None, cam_order="aligned", moves=None):
    """The canonical sequence. Returns (dump, placement, step log)."""
    d = copy.deepcopy(dump)
    steps = []
    n = whatif.shrink_pads(d, PAD_SHRINK)
    steps.append("pad shrink %s -> %d pad(s)" % (", ".join(PAD_SHRINK), n))
    whatif.repin_buses(d, "aligned")
    steps.append("bus repin (rank match both ends)")
    cam = list(cam_pads) if cam_pads else list(CAM_PADS)
    assign_block(d, "CAM_D", cam)
    if cam_order and cam_order != "aligned":
        # permute the group's nets across its own block: same pads, different pairing (§115)
        pads = [p for p in pads_of(d, PART) if pad_id(p) in cam]
        nets = [p.get("net") for p in pads]
        if cam_order == "reversed":
            new_nets = list(reversed(nets))
        elif cam_order.startswith("shift"):
            k = int(cam_order[5:] or 1) % len(nets)
            new_nets = nets[k:] + nets[:k]
        else:
            raise SystemExit("unknown cam-order %s" % cam_order)
        for p, n in zip(pads, new_nets):
            p["net"] = n
    steps.append("CAM_D -> %s on %s (%s order)" % (",".join(cam), PART, cam_order))
    assign_block(d, "SD_", SD_PADS)
    steps.append("SD_ -> %s on %s" % (",".join(SD_PADS), PART))
    whatif.repin_buses(d, "aligned")
    steps.append("bus repin again after the blocks")
    for a, b in LCD_SWAPS:
        swap_nets(d, a, b)
    steps.append("LCD pairing reversed (%s)" % ", ".join("%s<->%s" % s for s in LCD_SWAPS))

    p = copy.deepcopy(place)
    use_moves = dict(MOVES if moves is None else moves)
    for des, (dx, dy) in use_moves.items():
        p[des]["x"] = float(p[des]["x"]) + dx
        p[des]["y"] = float(p[des]["y"]) + dy
    steps.append("placement moves: " + ", ".join(
        "%s (%+.0f, %+.0f)" % (des, dx, dy) for des, (dx, dy) in use_moves.items()))
    return d, p, steps


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cam-order", default="aligned",
                    help="aligned | reversed | shift1..shift7 - pairing inside the CAM block")
    ap.add_argument("--cam-pads", default="",
                    help="comma list of U5 pads for the CAM block (default 13..20)")
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    with open(a.place, encoding="utf-8") as f:
        place = json.load(f)

    cam = [x.strip() for x in a.cam_pads.split(",") if x.strip()] or None
    d, p, steps = build(dump, place, cam, a.cam_order)
    os.makedirs(a.out_dir, exist_ok=True)
    dump_out = os.path.join(a.out_dir, "dump.json")
    place_out = os.path.join(a.out_dir, "place.json")
    with open(dump_out, "w", encoding="utf-8") as f:
        json.dump(d, f)
    with open(place_out, "w", encoding="utf-8") as f:
        json.dump(p, f)

    # running it twice must give the same bytes: that is the whole point of §113
    d2, p2, _ = build(dump, place, cam, a.cam_order)
    same = (json.dumps(d2, sort_keys=True) == json.dumps(d, sort_keys=True)
            and json.dumps(p2, sort_keys=True) == json.dumps(p, sort_keys=True))
    prov = {"inputs": {"dump": sha(a.dump), "place": sha(a.place)},
            "outputs": {"dump": sha(dump_out), "place": sha(place_out)},
            "idempotent": same, "steps": steps}
    with open(os.path.join(a.out_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, indent=1)

    print("recipe applied in one documented order (%s):" % a.out_dir)
    for i, s in enumerate(steps, 1):
        print("  %d. %s" % (i, s))
    print("  idempotent: %s" % ("YES" if same else "NO - FIX BEFORE QUOTING ANY NUMBER"))
    print("\nmeasure it (delivery grade, ~45 min):")
    print("   python easycirq/scripts/layout/reproduce.py --dump %s --place %s --profile strict-via-thin "
          "--out-dir out/recipe-run" % (dump_out, place_out))
    print("provenance: %s" % os.path.join(a.out_dir, "provenance.json"))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
