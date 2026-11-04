#!/usr/bin/env python3
"""A board the toolchain CAN take green - the capability proof behind D2 (GAPS).

RetroCam-02 cannot reach "clearance 0 + all bus groups matched" with its parts (HANDOFF §123); that is a
board fact, not a tool fact.  This module builds a small board **designed to be routable** (two connectors,
one pitch on both ends, short parallel nets, generous room) and runs the same pipeline on it:

  * if the gate goes green, the toolchain has demonstrated the capability end to end;
  * if it does NOT go green, that is a tool defect and this self-test is the regression.

It is not a product design and it is not "a delivered board" - it is the smallest board that lets the tool
show its green path, which is what a customer has to be able to see before trusting the red verdicts on
real boards.

Usage
-----
    python easycirq/scripts/layout/selftest.py [--out-dir OUT]      # build, route, report; exit 0 only if green
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ec_layout as ec  # noqa: E402
import reproduce as rep  # noqa: E402

PITCH = 50.0          # mil, both ends - the whole point of this board
GROUP = ["CAM_D%d" % i for i in range(8)]
BOARD = (1600.0, 900.0)


def make_dump():
    """Two 8-pin rows facing each other, one net per pad pair, lots of room around them."""
    comps = []
    for des, (cx, cy) in (("J1", (300.0, 450.0)), ("U1", (1300.0, 450.0))):
        pads = []
        for i, net in enumerate(GROUP):
            y = cy + (i - (len(GROUP) - 1) / 2.0) * PITCH
            pads.append({"padNumber": str(i + 1), "net": net, "x": cx, "y": y,
                         "width": 14.0, "height": 14.0, "layer": 1})
        comps.append({"designator": des, "x": cx, "y": cy, "rotation": 0.0,
                      "bbox": {"minX": cx - 30.0, "maxX": cx + 30.0,
                               "minY": cy - 4.5 * PITCH, "maxY": cy + 4.5 * PITCH},
                      "pads": pads})
    w, h = BOARD
    return {"result": {
        "components": comps,
        "outline": {"bbox": {"minX": 0.0, "minY": 0.0, "maxX": w, "maxY": h},
                    "points": [[0, 0], [w, 0], [w, h], [0, h]]},
        "copperLayers": 2,
        "rules": {"clearanceMil": 6.0, "clearanceTrackTrackMil": 6.0, "trackWidthMil": 6.0,
                  "powerWidthMil": 10.0, "trackWidthMinMil": 5.0, "viaDrillMil": 12.01,
                  # the router uses a 12.01 mil via radius; a board rule below that makes plan_lint
                  # (correctly) refuse the plan, which is what the second board taught us (HANDOFF §172)
                  "viaDiameterMil": 24.02, "copperToEdgeMil": 8.0},
    }}


def make_place():
    return {"J1": {"x": 300.0, "y": 450.0, "rotation": 0.0},
            "U1": {"x": 1300.0, "y": 450.0, "rotation": 0.0}}


def run(out_dir=None, iters=60, profile="strict-via-thin"):
    import tempfile

    tmp = out_dir or tempfile.mkdtemp(prefix="selftest-")
    os.makedirs(tmp, exist_ok=True)
    dump_path = os.path.join(tmp, "dump.json")
    place_path = os.path.join(tmp, "place.json")
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(make_dump(), f)
    with open(place_path, "w", encoding="utf-8") as f:
        json.dump(make_place(), f)

    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    rep.use_grid(cfg.get("grid"))
    import grid_experiment
    rep.ec = grid_experiment.load_module(float(cfg.get("grid") or 10),
                                        constants=cfg.get("constants"))
    with open(dump_path, encoding="utf-8") as f:
        board = rep.ec.Board(json.load(f))
    with open(place_path, encoding="utf-8") as f:
        rep.ec.apply_placement(board, json.load(f))
    routed, failures = rep._route(board, cfg)
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, failures, [], plan)
    ok, failing = rep.ec.gate(kpi)
    skew = kpi["bus_length_spread_mil"]
    return {"dir": tmp, "kpi": {k: kpi[k] for k in
                                ("unrouted_legs", "congestion_cells", "nets_unconnected",
                                 "clearance_violations", "pad_layer_gaps", "pour_islands")},
            "skew": skew, "gate_pass": ok, "failing": failing,
            "skew_pass": all(v < 50 for v in skew.values()), "plan": plan}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir")
    ap.add_argument("--iters", type=int, default=60)
    a = ap.parse_args()
    res = run(a.out_dir, a.iters)
    print("self-test board (two 8-pin rows at %.0f mil pitch, %dx%d mil)" % (PITCH, BOARD[0], BOARD[1]))
    print("| KPI | value |")
    print("|---|---|")
    for k, v in res["kpi"].items():
        print("| %s | %s |" % (k, v))
    print("| bus skew | %s |" % (res["skew"],))
    print("\ngate: %s%s | skew: %s" % (
        "PASS" if res["gate_pass"] else "FAIL",
        "" if res["gate_pass"] else " (%s)" % ", ".join(res["failing"]),
        "ALL WITHIN 50 mil" if res["skew_pass"] else "over 50 mil"))
    print("artefacts: %s" % res["dir"])
    if res["gate_pass"] and res["skew_pass"]:
        print("\nThe toolchain reached a green gate on a board that allows it - the red verdicts on "
              "RetroCam-02 are a board fact, not a tool limit.")
        return 0
    print("\nA board designed to be routable did NOT reach a green gate: that is a tool defect, "
          "fix it before trusting any red verdict elsewhere.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
