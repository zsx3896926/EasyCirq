#!/usr/bin/env python3
"""Named board candidates: "board change + recipe + moves" as one reproducible object (GAPS G4).

A candidate is the combination the effort converged on, recorded as data instead of a shell history:

  board change   outline grown, pads resized              (board_change.build)
  recipe         bus repin, joint pin blocks, LCD pairing reversal, placement moves (prescribe.build)

`pipeline.py --candidate NAME` uses this module, builds the pair into its out directory, routes it and
writes the delivery report - so "the best measured configuration" is one command and carries provenance.

Add a candidate here when a new combination is measured; never hand-edit the outputs.

Usage
-----
    python easycirq/scripts/layout/candidates.py --dump dump2.json --place ec-placed.json \
        --candidate frontier-d --out-dir out/fd        # build only
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_change  # noqa: E402
import ec_layout  # noqa: E402
import place_repair  # noqa: E402
import prescribe  # noqa: E402

# Each entry mirrors a measured section of HANDOFF; update the comment when the numbers move.
CANDIDATES = {
    # §122/§123: the best measured point - 0/0/0/0/0 gate items, clearance 345,
    # skew CAM 80.0 / LCD 41.4 / SD 31.9 at the delivery profile.
    "frontier-d": {
        # DEPRECATED_ILLEGAL: this placement has overlapping parts (§143-§147 audit);
        # its numbers are routing-stage upper bounds only, not deliverable evidence.
        "deprecated_illegal": True,
        "board": {"grow": 500.0, "spread": 1.0},
        # §122 used place_repair to remove the last unreachable pad on the enlarged board
        # (U4 -30/+30).  Leaving it out is what made the first version of this candidate differ
        # from the measured point, so it is part of the definition.
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["13", "14", "15", "16", "17", "18", "19", "20"],
                   "cam_order": "aligned",
                   "moves": {"J3": (-190.0, 0.0), "J4": (120.0, 100.0)}},
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 345,
                     "bus_length_spread_mil": {"CAM_D": 80.0, "LCD_": 41.4, "SD_": 31.9},
                     # delivery-grade shape metrics (§122): L1 share and the 45-degree share
                     "diagonal_ratio": 0.430,
                     "layer_share": {"1": 54.4, "2": 30.2, "3": 5.9, "4": 9.5}},
        # the 25-pass screen used by regress.py measures slightly different numbers; keeping them
        # separate is what stops the gate from crying wolf on iteration count alone
        "measured_screen": {"clearance_violations": 345,
                            "bus_length_spread_mil": {"CAM_D": 80.0, "LCD_": 41.4, "SD_": 31.9},
                            "diagonal_ratio": 0.434,
                            "layer_share": {"1": 49.5, "2": 31.6, "3": 12.0, "4": 6.9}},
        "section": "§122/§123",
    },
    # §133: frontier-d with the power nets widened to 12 mil, which the IPC-2221 check (§132) needs
    # for a 1 A / 10 C-rise net.  Measured cost in the 25-pass screen: clearance 345 -> 358, everything
    # else unchanged.
    "frontier-e": {
        # DEPRECATED_ILLEGAL: this placement has overlapping parts (§143-§147 audit);
        # its numbers are routing-stage upper bounds only, not deliverable evidence.
        "deprecated_illegal": True,
        "board": {"grow": 500.0, "spread": 1.0},
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["13", "14", "15", "16", "17", "18", "19", "20"],
                   "cam_order": "aligned",
                   "moves": {"J3": (-190.0, 0.0), "J4": (120.0, 100.0)}},
        "constants": {"POWER_TRACE": 12.0},
        # delivery-grade run (70 passes, §134): clearance 358, L1 share 49.4 %,
        # power nets at 12 mil carry 1.01 A at a 10 C rise (the IPC-2221 check passes)
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 358,
                     "bus_length_spread_mil": {"CAM_D": 80.0, "LCD_": 41.4, "SD_": 31.9},
                     "diagonal_ratio": 0.434,
                     "layer_share": {"1": 49.4, "2": 31.7, "3": 12.0, "4": 6.9}},
        "measured_screen": {"clearance_violations": 358,
                            "bus_length_spread_mil": {"CAM_D": 80.0, "LCD_": 41.4, "SD_": 31.9},
                            "diagonal_ratio": 0.434,
                            "layer_share": {"1": 49.5, "2": 31.6, "3": 12.0, "4": 6.9}},
        "section": "§133",
    },
    # §137: frontier-e plus smaller connector (J1/J3 20 mil) and SoC (U5 36 mil) pads.  Measured in the
    # 25-pass screen: clearance 358 -> 205 with zero congestion and the skew unchanged.
    "frontier-f": {
        # DEPRECATED_ILLEGAL: this placement has overlapping parts (§143-§147 audit);
        # its numbers are routing-stage upper bounds only, not deliverable evidence.
        "deprecated_illegal": True,
        "board": {"grow": 500.0, "spread": 1.0},
        "extra_pads": ["J1=20x20", "J3=20x20", "U5=36x36"],
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["13", "14", "15", "16", "17", "18", "19", "20"],
                   "cam_order": "aligned",
                   "moves": {"J3": (-190.0, 0.0), "J4": (120.0, 100.0)}},
        "constants": {"POWER_TRACE": 12.0},
        # delivery-grade run (§137): clearance 205 (-43 % vs frontier-e), but the L1 share rose to
        # 56.5 % and the 45-degree share fell to 0.423 - shorter copper concentrates on the top layer.
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 205,
                     "bus_length_spread_mil": {"CAM_D": 88.3, "LCD_": 41.4, "SD_": 31.9},
                     "diagonal_ratio": 0.423,
                     "layer_share": {"1": 56.5, "2": 25.6, "3": 9.1, "4": 8.8}},
        "measured_screen": {"clearance_violations": 205,
                            "bus_length_spread_mil": {"CAM_D": 88.3, "LCD_": 41.4, "SD_": 31.9},
                            "diagonal_ratio": 0.423,
                            "layer_share": {"1": 56.5, "2": 25.6, "3": 9.1, "4": 8.8}},
        "section": "§137",
    },
    # §145: the first candidate whose placement is LEGAL (n_overlaps 0, n_outside 0) and whose pad
    # sizes are manufacturable: J1/J3 pads 12x16 on their 19.7 mil pitch (width must stay below the
    # pitch - 20 mil was not), U5 pads 36x36, J3 NOT shifted (any left shift overlaps U5).
    # 25-pass screen: clearance 166, CAM 157.1 / LCD 41.4 / SD 31.9, zero on every other gate item.
    "frontier-g": {
        "board": {"grow": 500.0, "spread": 1.0},
        "extra_pads": ["J1=12x16", "J3=12x16", "U5=36x36"],
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["13", "14", "15", "16", "17", "18", "19", "20"],
                   "cam_order": "aligned",
                   "moves": {"J3": (0.0, 0.0), "J4": (120.0, 100.0)}},
        "constants": {"POWER_TRACE": 12.0},
        # delivery-grade run with a LEGAL placement (overlaps 0 / outside 0, §146):
        # clearance 180, CAM 398.6 / LCD 41.4 / SD 31.9, L1 share 56.0 %, 45-degree 0.436
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 180,
                     "bus_length_spread_mil": {"CAM_D": 398.6, "LCD_": 41.4, "SD_": 31.9},
                     "diagonal_ratio": 0.436,
                     "layer_share": {"1": 56.0, "2": 24.7, "3": 7.9, "4": 11.4}},
        # screen values after the overlap-aware repair change (it now picks U4 (+40,0))
        "measured_screen": {"clearance_violations": 168,
                            "bus_length_spread_mil": {"CAM_D": 157.1, "LCD_": 41.4, "SD_": 31.9}},
        "section": "§145",
    },
    # §147/§149: the second legal trade-off point - a tighter SoC pad (26 mil) trades clearance for bus
    # skew: 25-pass screen gave clearance 209 with CAM 124.0 (frontier-g has 168 / 157.1).
    "frontier-h": {
        "board": {"grow": 500.0, "spread": 1.0},
        "extra_pads": ["J1=12x16", "J3=12x16", "U5=26x26"],
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["13", "14", "15", "16", "17", "18", "19", "20"],
                   "cam_order": "aligned",
                   "moves": {"J3": (0.0, 0.0), "J4": (120.0, 100.0)}},
        "constants": {"POWER_TRACE": 12.0},
        # delivery grade (§149): clearance 232, CAM 144.9 / LCD 41.4 / SD 31.9, L1 55.6 %, 45-deg 0.410
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 232,
                     "bus_length_spread_mil": {"CAM_D": 144.9, "LCD_": 41.4, "SD_": 31.9},
                     "diagonal_ratio": 0.410,
                     "layer_share": {"1": 55.6, "2": 24.9, "3": 8.7, "4": 10.8}},
        "measured_screen": {"clearance_violations": 209,
                            "bus_length_spread_mil": {"CAM_D": 124.0, "LCD_": 41.4, "SD_": 31.9}},
        "section": "§147/§149",
    },
    # §155: legal window screen on the frontier-h geometry.  The documented ranking puts clearance above
    # skew, and the 17..24 window reached the best legal clearance seen (146 at the 25-pass screen) at the
    # cost of a bad CAM skew (837.8).  11..18 gives the best CAM (121.8) but clearance 217.
    "frontier-i": {
        "board": {"grow": 500.0, "spread": 1.0},
        "extra_pads": ["J1=12x16", "J3=12x16", "U5=26x26"],
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["17", "18", "19", "20", "21", "22", "23", "24"],
                   "cam_order": "aligned",
                   "moves": {"J3": (0.0, 0.0), "J4": (120.0, 100.0)}},
        "constants": {"POWER_TRACE": 12.0},
        # delivery grade (§155): clearance 146 (the best legal figure so far), CAM 837.8,
        # LCD 41.4 / SD 31.9, L1 53.2 %, 45-degree 0.399.  By the documented ranking (clearance above
        # skew) this is the best legal point; by CAM skew it is the worst.
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 146,
                     "bus_length_spread_mil": {"CAM_D": 837.8, "LCD_": 41.4, "SD_": 31.9},
                     "diagonal_ratio": 0.399,
                     "layer_share": {"1": 53.2, "2": 27.4, "3": 8.1, "4": 11.3}},
        "measured_screen": {"clearance_violations": 146,
                            "bus_length_spread_mil": {"CAM_D": 837.8, "LCD_": 41.4, "SD_": 31.9}},
        "section": "§155",
        # D8 (user decision, 2026-11-03): the ranking puts clearance before skew, so this is the PRIMARY
        # candidate; frontier-j remains the comparison point with the best CAM skew.
        "primary": True,
    },
    # §155/§156: the other end of the CAM window trade-off - window 11..18 gave the best CAM skew of the
    # legal screen (121.8) with clearance 217.  Together with frontier-i this bounds the curve.
    "frontier-j": {
        "board": {"grow": 500.0, "spread": 1.0},
        "extra_pads": ["J1=12x16", "J3=12x16", "U5=26x26"],
        "repair": {"width": 5.0, "clearance": 6.0, "step": 10.0, "radius": 120.0},
        "recipe": {"cam_pads": ["11", "12", "13", "14", "15", "16", "17", "18"],
                   "cam_order": "aligned",
                   "moves": {"J3": (0.0, 0.0), "J4": (120.0, 100.0)}},
        "constants": {"POWER_TRACE": 12.0},
        # delivery grade (§156): clearance 217, CAM 121.8 (best of the four legal points), L1 52.5 %, 45 0.427
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 217,
                     "bus_length_spread_mil": {"CAM_D": 121.8, "LCD_": 41.4, "SD_": 31.9},
                     "diagonal_ratio": 0.427,
                     "layer_share": {"1": 52.5, "2": 26.1, "3": 10.1, "4": 11.3}},
        "measured_screen": {"clearance_violations": 217,
                            "bus_length_spread_mil": {"CAM_D": 121.8, "LCD_": 41.4, "SD_": 31.9}},
        "section": "§155/§156",
    },
    # §114/§118: the recipe on the original board - reproducible baseline, clearance 368,
    # CAM 1543.7 (one runaway net), LCD 41.4, SD 31.9.
    "recipe-only": {
        # DEPRECATED_ILLEGAL: this placement has overlapping parts (§143-§147 audit);
        # its numbers are routing-stage upper bounds only, not deliverable evidence.
        "deprecated_illegal": True,
        "board": None,
        "recipe": {"cam_pads": None, "cam_order": "aligned", "moves": None},
        "measured": {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                     "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 368,
                     "bus_length_spread_mil": {"CAM_D": 1543.7, "LCD_": 41.4, "SD_": 31.9}},
        "section": "§114/§118",
    },
}


def constants_for(name):
    """Design constants a candidate needs on top of the profile (e.g. a wider power trace)."""
    spec = CANDIDATES.get(name) or {}
    return dict(spec.get("constants") or {})


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "candidates")


def _cache_key(name, dump, place):
    h = hashlib.sha256()
    h.update(name.encode())
    h.update(json.dumps(dump, sort_keys=True).encode())
    h.update(json.dumps(place, sort_keys=True).encode())
    return h.hexdigest()[:20]


def build(name, dump, place, use_cache=None):
    """Return (dump, place, provenance) for a candidate. Deterministic by construction.

    The build is ~9.6 s on RetroCam, almost all of it in `place_repair` (`escape_check`), and it depends
    only on (candidate, dump, placement) - so it is memoised on a content hash (HANDOFF §182).  Disable with
    CANDIDATES_NO_CACHE=1 or `use_cache=False`.
    """
    if use_cache is None:
        use_cache = os.environ.get("CANDIDATES_NO_CACHE") != "1"
    key = _cache_key(name, dump, place)
    cache_path = os.path.join(CACHE_DIR, key + ".json")
    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                hit = json.load(f)
            return hit["dump"], hit["place"], hit["provenance"]
        except (OSError, ValueError, KeyError):
            pass                                   # a corrupt cache entry must never break a build
    d, p, prov = _build_uncached(name, dump, place)
    if use_cache:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"dump": d, "place": p, "provenance": prov}, f)
        except OSError:
            pass
    return d, p, prov


def _build_uncached(name, dump, place):
    """The actual (unchanged) build - see build() for the cached entry point."""
    if name not in CANDIDATES:
        raise SystemExit("unknown candidate %r (have: %s)" % (name, ", ".join(sorted(CANDIDATES))))
    spec = CANDIDATES[name]
    steps = []
    d = dump
    p = place
    if spec["board"]:
        d, p, meta = board_change.build(d, p, spec["board"]["grow"], spec["board"]["spread"])
        steps.append("board change: grow %s, spread %s, pads %s" % (
            spec["board"]["grow"], spec["board"]["spread"], ", ".join(board_change.PAD_SHRINK)))
    if spec.get("extra_pads"):
        # smaller connector / SoC pads (§137): the biggest single lever found for clearance
        import whatif as _whatif
        n_extra = _whatif.shrink_pads(d, spec["extra_pads"])
        steps.append("extra pad shrink: %s (%d pads)" % (", ".join(spec["extra_pads"]), n_extra))
    if spec.get("repair"):
        r = spec["repair"]
        moves, _board = place_repair.repair(d, p, r["width"], r["clearance"], r["step"],
                                            r["radius"], verbose=False)
        for des, (dx, dy) in moves.items():
            p[des]["x"] = float(p[des]["x"]) + dx
            p[des]["y"] = float(p[des]["y"]) + dy
        steps.append("placement repair: " + (", ".join(
            "%s (%+.0f, %+.0f)" % (des, dx, dy) for des, (dx, dy) in sorted(moves.items()))
            or "nothing to repair"))
    d, p, recipe_steps = prescribe.build(
        d, p, spec["recipe"]["cam_pads"], spec["recipe"]["cam_order"], spec["recipe"]["moves"])
    steps.extend(recipe_steps)
    prov = {"candidate": name, "section": spec["section"], "steps": steps,
            "measured": spec["measured"]}
    return d, p, prov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--candidate", required=True, choices=sorted(CANDIDATES))
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    with open(a.place, encoding="utf-8") as f:
        place = json.load(f)
    d, p, prov = build(a.candidate, dump, place)
    d2, p2, _ = build(a.candidate, dump, place)
    same = (json.dumps(d, sort_keys=True) == json.dumps(d2, sort_keys=True)
            and json.dumps(p, sort_keys=True) == json.dumps(p2, sort_keys=True))

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "dump.json"), "w", encoding="utf-8") as f:
        json.dump(d, f)
    with open(os.path.join(a.out_dir, "place.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)
    prov["idempotent"] = same
    with open(os.path.join(a.out_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, indent=1)

    print("candidate %s (%s) -> %s" % (a.candidate, prov["section"], a.out_dir))
    for i, step in enumerate(prov["steps"], 1):
        print("  %d. %s" % (i, step))
    print("  idempotent: %s" % ("YES" if same else "NO"))
    print("  measured when recorded: %s" % json.dumps(prov["measured"]))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
