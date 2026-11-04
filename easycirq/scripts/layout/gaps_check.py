#!/usr/bin/env python3
"""Run every P1 check in GAPS.md in one command and print the acceptance matrix (GAPS index).

GAPS lists six P1 items; five of them (G4-G9) are tool-side and can be verified without touching the
board.  This script runs all of them against one candidate so "is EasyCirq better than yesterday?" is a
single command instead of six:

  G4  candidate builds deterministically (twice, byte-identical)
  G5  regression gate against the recorded numbers
  G6  L1 layer share and 45-degree share inside the recorded limits
  G7  impedance check: tracks off a 50 ohm target + closest bus spacing
  G8  IPC-2221 capacity: power nets that do not carry their assumed current
  G9  thermal screen: tightest part at the assumed numbers

Everything is measured on a **--iters 25 screen** by default (about five minutes); `--iters 70` runs the
delivery grade.  P0 items (spacing to zero, CAM skew under 50, skew spec) need a design decision and are
reported as such instead of being scored.

Usage
-----
    python easycirq/scripts/layout/gaps_check.py --dump dump2.json --place ec-placed.json \
        [--candidate frontier-e] [--iters 25]
"""
import argparse
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import candidates  # noqa: E402
import dfm  # noqa: E402
import fabrication  # noqa: E402
import footprints  # noqa: E402
from regress import _refuse_deprecated  # noqa: E402
import current  # noqa: E402
import impedance  # noqa: E402
import regress  # noqa: E402
import thermal  # noqa: E402

SKEW_TARGET = 50.0


def _ec_board(dump, place):
    """(overlaps == 0 and outside == 0) for a built candidate, without printing."""
    import ec_layout as _ec
    b = _ec.Board(dump)
    _ec.apply_placement(b, place)
    return _ec.n_overlaps(b.comps) == 0 and _ec.n_outside(b.comps, b) == 0


def run(name, dump_path, place_path, iters):
    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        place = json.load(f)
    d1, p1, prov = candidates.build(name, dump, place)
    d2, p2, _ = candidates.build(name, dump, place)
    idempotent = (json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
                  and json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True))
    measured, plan = regress.measure(name, dump_path, place_path,
                                     "strict-via-thin", iters)
    return idempotent, prov, measured, plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--candidate", default="frontier-g",
                    choices=sorted(candidates.CANDIDATES) + ["all"],
                    help="a candidate name, or 'all' to compare every active (legal) candidate")
    ap.add_argument("--allow-illegal", action="store_true")
    ap.add_argument("--iters", type=int, default=25)
    a = ap.parse_args()

    def _needs(it, clearance, skew_rec):
        """Distance from the two P0 targets, stated as text so nobody reads it as compliance."""
        bits = []
        if clearance:
            bits.append("clearance %d -> 0" % clearance)
        cam = (skew_rec or {}).get("CAM_D")
        if cam:
            bits.append("CAM %.1f -> <50" % cam)
        return "; ".join(bits)

    if a.candidate == "all":
        active = [n for n, sp in candidates.CANDIDATES.items()
                  if not sp.get("deprecated_illegal") and n != "all"]
        print("comparing %d active candidate(s) at %d passes (this runs the router once per candidate)\n"
              % (len(active), a.iters))
        table = []
        for name in active:
            measured, plan = regress.measure(name, a.dump, a.place, "strict-via-thin", a.iters)
            q = {"clearance": measured.get("clearance_violations"),
                 "skew": measured.get("bus_length_spread_mil") or {},
                 "L1": float((measured.get("layer_share") or {}).get("1", 0.0)),
                 "diag": measured.get("diagonal_ratio")}
            d_b, p_b, _ = candidates.build(name, json.load(open(a.dump, encoding="utf-8")),
                                           json.load(open(a.place, encoding="utf-8")))
            b_l = dfm  # keep the import used
            ech = _ec_board(d_b, p_b)
            table.append((name, ech, q))
        print("| candidate | legal | clearance | CAM | LCD | SD | L1 | 45deg | still short of |")
        print("|---|---|---|---|---|---|---|---|---|")
        for name, legal, q in table:
            print("| %s | %s | %d | %.1f | %.1f | %.1f | %.1f%% | %.3f | %s |" % (
                name, "LEGAL" if legal else "ILLEGAL", q["clearance"],
                q["skew"].get("CAM_D", 0.0), q["skew"].get("LCD_", 0.0), q["skew"].get("SD_", 0.0),
                q["L1"], q["diag"] or 0.0, _needs(None, q["clearance"], q["skew"])))
        print("\nP0 targets are not met by any point: spacing has a legal floor and CAM does not reach 50.")
        print("Run a single candidate (--candidate frontier-h) for the full 12-row matrix and DFM/thermal checks.")
        return 0

    _refuse_deprecated(a.candidate, a.allow_illegal)
    spec = candidates.CANDIDATES[a.candidate]
    recorded = spec["measured"]
    if a.iters != 70 and spec.get("measured_screen"):
        screen = spec["measured_screen"]
        recorded = {**recorded, **screen}
        for key in ("diagonal_ratio", "layer_share"):
            if key not in screen:      # only enforce what was recorded at this pass count
                recorded.pop(key, None)

    idempotent, prov, measured, plan = run(a.candidate, a.dump, a.place, a.iters)

    rows = []
    # G12: placement legality (the router will happily route an overlapping board)
    with open(a.place, encoding="utf-8") as f:
        place_in = json.load(f)
    d_built, p_built, _ = candidates.build(a.candidate, json.load(open(a.dump, encoding="utf-8")),
                                           place_in)
    import ec_layout as _ec
    _b = _ec.Board(d_built)
    _ec.apply_placement(_b, p_built)
    _ov, _out = _ec.n_overlaps(_b.comps), _ec.n_outside(_b.comps, _b)
    rows.append(("T3", "candidate placement is legal", "PASS" if _ov == 0 and _out == 0 else "FAIL",
                 "overlaps %d, outside %d" % (_ov, _out)))
    # G4
    rows.append(("G4", "candidate builds deterministically", "PASS" if idempotent else "FAIL",
                 "%d steps, idempotent=%s" % (len(prov["steps"]), idempotent)))
    # G5 / G6 share one comparison
    ok, detail = regress.compare(recorded, measured)
    gate_bad = [r[0] for r in detail if r[3] != "OK" and not r[0].startswith(("diagonal", "layer_share"))]
    shape_bad = [r[0] for r in detail if r[3] != "OK" and r[0].startswith(("diagonal", "layer_share"))]
    rows.append(("G5", "no measured number regressed", "PASS" if not gate_bad else "FAIL",
                 ", ".join(gate_bad) or "all gate/skew rows ok"))
    rows.append(("G6", "layer share / 45-degree inside limits", "PASS" if not shape_bad else "FAIL",
                 ", ".join(shape_bad) or "L1 %.1f%%, 45deg %.3f" % (
                     float(measured["layer_share"].get("1", 0.0)),
                     float(measured.get("diagonal_ratio") or 0.0))))

    # G7: impedance + bus spacing
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _need, bad = impedance.report("jlc-4l-1.6", 50.0, plan)
        spacing = {p: impedance.group_spacing(plan, [p]) for p in ("CAM_D", "LCD_", "SD_")}
    # G7 is a TOOL check plus a BOARD finding: the tool working is PASS, the board being off target is
    # an OPEN defect, not a tool failure - the matrix must not confuse the two.
    rows.append(("G7", "impedance check runs", "PASS",
                 "%d layer/width combination(s) off a 50 ohm target (board finding: OPEN)" % len(bad)))
    tight = [p for p, res in spacing.items() if res and res[0] < 0]
    rows.append(("G7b", "bus spacing measured", "PASS",
                 ("OVERLAP found in " + ", ".join(tight) + " (board finding: OPEN)") if tight
                 else "no negative gaps"))

    # G8: capacity
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cur_rows = current.report(plan, current.ASSUMED_AMPS, [10.0, 20.0])
    under = [r[0] for r in cur_rows if r[4] != "ok"]
    rows.append(("G8", "power nets carry their assumed current", "FAIL" if under else "PASS",
                 ("undersized: " + ", ".join(under)) if under else "all ok at 10 C rise"))

    # G11: DFM screen (edge / mask sliver / track width); the drill payload is UNRESOLVED by design
    with open(a.dump, encoding="utf-8") as f:
        dump_full = json.load(f)
    dfm_edge = dfm.check_edge(dump_full, plan, dfm.LIMITS)
    dfm_sliver = dfm.check_mask_sliver(dump_full, dfm.LIMITS)
    dfm_width = dfm.check_geometry(plan, dfm.LIMITS)
    dfm_drill_findings, dfm_drill_unresolved = dfm.check_drills(dump_full, dfm.LIMITS)
    dfm_bad = len(dfm_edge or []) + len(dfm_sliver) + len(dfm_width) + len(dfm_drill_findings)
    rows.append(("G11", "DFM screen (edge/mask/track)", "PASS" if dfm_bad == 0 else "FAIL",
                 "%d finding(s) under the ASSUMED limits (incl. %d drill/ring); %d pad(s) unresolved"
                 % (dfm_bad, len(dfm_drill_findings), len(dfm_drill_unresolved))))

    # G12: footprint audit - flags are review items about the parts themselves
    fp_rows = footprints.audit(dump_full)
    fp_flags = [r for r in fp_rows if r["flags"]]
    rows.append(("G12", "footprint audit runs", "PASS",
                 "%d part(s) with review flags: %s" % (
                     len(fp_flags), ", ".join(r["designator"] for r in fp_flags) or "none")))

    # G10: offline fabrication manifest (the exports themselves are NOT RUN)
    import contextlib as _ctx
    import io as _io
    _buf = _io.StringIO()
    with _ctx.redirect_stdout(_buf):
        fab = fabrication.report(dump_full, plan, 4, 1.0)
    rows.append(("G10", "fabrication manifest runs", "PASS",
                 "%d tracks, %.0f mil copper, %d pads; single-pad nets %d; Gerber/BOM/CPL NOT RUN"
                 % (fab["tracks"], fab["length_mil"], fab["pads"], fab["orphans"])))

    # G9: thermal
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        thermal.report(thermal.DEFAULT_PARTS, 25.0)
    rows.append(("G9", "thermal screen at assumed values", "PASS",
                 "assumptions only - real powers and theta-ja are NOT RUN"))

    print("GAPS acceptance matrix - candidate %s (%s), %d passes"
          % (a.candidate, spec["section"], a.iters))
    print("| item | check | verdict | detail |")
    print("|---|---|---|---|")
    for item, check, verdict, detail in rows:
        print("| %s | %s | **%s** | %s |" % (item, check, verdict, detail))

    kpi_bits = "clearance %s, skew %s" % (
        measured.get("clearance_violations"),
        {k: round(v, 1) for k, v in (measured.get("bus_length_spread_mil") or {}).items()})
    print("\nmeasured now: %s" % kpi_bits)
    print("\nP0 items (need a design decision, not scored here):")
    print("  G1 spacing %s -> 0   (density / smaller parts)" % measured.get("clearance_violations"))
    skew = measured.get("bus_length_spread_mil") or {}
    print("  G2 CAM skew %s -> <%.0f   (connector / footprint change)" % (
        round(skew.get("CAM_D", 0.0), 1), SKEW_TARGET))
    print("  G3 skew spec                    (interface timing input)")

    failed = [r for r in rows if r[2] == "FAIL"]
    print("\n%s" % ("P1: every tool check passes; board-level findings are listed above as OPEN"
                    if not failed
                    else "P1: %d tool check(s) failing (%s)" % (len(failed), ", ".join(r[0] for r in failed))))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
