#!/usr/bin/env python3
"""One command that runs the whole offline chain and reports where it stands.

An agent (or a person) should not have to know the order of six tools to find out whether a
board is deliverable.  This runs the chain the docs describe:

    route -> KPIs -> spacing audit -> pour audit -> plan_lint -> delivery gate

and writes `report.md` plus `summary.json` into the out directory, exiting 0 only when the
gate is green.  It adds no measurement of its own: every number is produced by the tool that
owns it, so the report cannot drift from what the individual commands say.

Usage
-----
    python easycirq/scripts/layout/pipeline.py --dump dump2.json --place placed.json --out-dir out/run1 \
        [--profile strict-via-thin|thin-10mil] [--stackup 4]

The default profile is the deliverable-grade one (`strict-via-thin`, 5 mil grid, ~40 min) because
this command exists to answer "is it deliverable"; `--profile thin-10mil` is the fast iteration
setting (~6-14 min) and is one congestion cell short of a clean answer.
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
import normalise  # noqa: E402
import ec_layout as ec  # noqa: E402
import plan_lint  # noqa: E402
import reproduce as rep  # noqa: E402
import spacing_audit  # noqa: E402

GATE_KEYS = ("unrouted_legs", "congestion_cells", "clearance_violations",
             "nets_unconnected", "pad_layer_gaps", "pour_islands")


def run(dump_path, place_path, out_dir, profile="strict-via-thin", stackup=4, candidate=None):
    os.makedirs(out_dir, exist_ok=True)
    if candidate:
        # GAPS G4: a named candidate (board change + recipe + moves) is built here, so the
        # "best measured configuration" is one command instead of a shell history.
        with open(dump_path, encoding="utf-8") as f:
            dump_in = json.load(f)
        with open(place_path, encoding="utf-8") as f:
            place_in = json.load(f)
        dump_out = os.path.join(out_dir, "candidate-dump.json")
        place_out = os.path.join(out_dir, "candidate-place.json")
        d_built, p_built, prov = candidates.build(candidate, dump_in, place_in)
        with open(dump_out, "w", encoding="utf-8") as f:
            json.dump(d_built, f)
        with open(place_out, "w", encoding="utf-8") as f:
            json.dump(p_built, f)
        with open(os.path.join(out_dir, "candidate-provenance.json"), "w", encoding="utf-8") as f:
            json.dump(prov, f, indent=1)
        dump_path, place_path = dump_out, place_out
    if candidate:
        overrides = candidates.constants_for(candidate)
        if overrides:
            prof = dict(rep.PROFILES[profile])
            prof["constants"] = {**prof.get("constants", {}), **overrides}
            rep.PROFILES["_candidate"] = prof
            profile = "_candidate"
    # GAPS D1: shift a negative-frame capture into a positive one before building the board here too
    # (rep.run does the same for its own copy).
    with open(dump_path, encoding="utf-8") as f:
        _d = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        _p = json.load(f)
    _d, _p, _offset = normalise.apply(_d, _p)
    if _offset != (0.0, 0.0):
        print("normalised capture origin by (%+.1f, %+.1f) mil" % _offset)
        dump_path = os.path.join(out_dir, "normalised-dump.json")
        place_path = os.path.join(out_dir, "normalised-place.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(_d, f)
        with open(place_path, "w", encoding="utf-8") as f:
            json.dump(_p, f)

    kpi, skew, ok, failing, why = rep.run(dump_path, place_path, out_dir, profile=profile)

    with open(os.path.join(out_dir, "plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    with open(dump_path, encoding="utf-8") as f:
        board = ec.Board(json.load(f))

    # GAPS G12: a placement with overlapping parts is not manufacturable, and nothing used to check it.
    # The router happily routes an illegal board, so the gate has to look.
    with open(os.path.join(out_dir, "candidate-place.json") if candidate else place_path,
              encoding="utf-8") as f:
        placed = json.load(f)
    ec.apply_placement(board, placed)
    overlaps = ec.n_overlaps(board.comps)
    outside = ec.n_outside(board.comps, board)

    # the offline checks a fabricator/assembler asks about: DFM, footprints, and the manifest
    with open(dump_path, encoding="utf-8") as f:
        dump_now = json.load(f)
    dfm_edge = dfm.check_edge(dump_now, plan, dfm.LIMITS)
    dfm_sliver = dfm.check_mask_sliver(dump_now, dfm.LIMITS)
    dfm_width = dfm.check_geometry(plan, dfm.LIMITS)
    dfm_drill_findings, dfm_drill_unresolved = dfm.check_drills(dump_now, dfm.LIMITS)
    fp_flags = [r["designator"] for r in footprints.audit(dump_now) if r["flags"]]
    fs = io.StringIO()
    with contextlib.redirect_stdout(fs):
        fab = fabrication.report(dump_now, plan, stackup, 1.0)

    lint = plan_lint.lint(board, plan, stackup=stackup)
    lint_bad = [(name, detail) for (name, okf, detail) in lint if okf is False]

    with open(os.path.join(out_dir, "kpi.json"), encoding="utf-8") as f:
        kpi_doc = json.load(f)
    groups = spacing_audit.group_violations(board, plan, top=5)

    gate_red = [k for k in GATE_KEYS if kpi.get(k)]
    summary = {
        "profile": profile,
        "gate": "FAIL" if gate_red else "PASS",
        "failing_gate_keys": gate_red,
        "kpi": {k: kpi.get(k) for k in GATE_KEYS},
        "info": {k: kpi.get(k) for k in ("vias", "plane_vias", "vias_in_pad", "tracks",
                                         "total_length_mil", "diagonal_ratio",
                                         "layer_length_mil", "bus_length_spread_mil")},
        "skew": skew,
        "dfm": {"edge": len(dfm_edge or []), "mask": len(dfm_sliver),
                "width": len(dfm_width), "drill_findings": len(dfm_drill_findings),
                "drill_unresolved": len(dfm_drill_unresolved)},
        "footprints": {"flagged": fp_flags},
        "fabrication": fab,
        "placement": {"overlaps": overlaps, "outside": outside,
                      "legal": overlaps == 0 and outside == 0},
        "plan_lint": {"verdict": "FAIL" if lint_bad else "PASS",
                      "failing": [{"check": n, "detail": d} for n, d in lint_bad]},
        "skew_target_met": ok,
        "deliverable": ((not gate_red) and not lint_bad and overlaps == 0 and outside == 0
                        and len(dfm_edge or []) == 0 and len(dfm_sliver) == 0
                        and len(dfm_width) == 0 and len(dfm_drill_findings) == 0),
    }
    if candidate:
        summary["candidate"] = {"name": candidate, **prov}
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(_report(summary, len(groups or {})))
    return summary


def _report(s, group_count):
    k = s["kpi"]
    i = s["info"]
    lines = [
        "# Offline layout & routing report",
        "",
        "profile `%s`" % s["profile"],
        "",
        "## Gate",
        "",
        "| KPI | value | |",
        "|---|---|---|",
    ]
    for key in GATE_KEYS:
        lines.append("| %s | %s | %s |" % (key, k.get(key),
                                           "**red**" if k.get(key) else "ok"))
    lines += [
        "",
        "**verdict: %s**%s" % (s["gate"],
                               "" if not s["failing_gate_keys"]
                               else "  (red: %s)" % ", ".join(s["failing_gate_keys"])),
        "",
        "## Info",
        "",
        "| KPI | value |",
        "|---|---|",
    ]
    for key, val in i.items():
        lines.append("| %s | %s |" % (key, val))
    lines += ["| bus skew (mil) | %s |" % (s["skew"],), ""]
    placement = s.get("placement")
    if placement:
        lines += [
            "## Placement legality",
            "",
            "**%s** - overlaps %d, outside %d" % (
                "LEGAL" if placement["legal"] else "ILLEGAL",
                placement["overlaps"], placement["outside"]),
            "",
        ]
    dfm_info = s.get("dfm")
    if dfm_info:
        lines += [
            "## DFM screen",
            "",
            "- copper to edge: **%d** finding(s)" % dfm_info["edge"],
            "- soldermask sliver: **%d** finding(s)" % dfm_info["mask"],
            "- track width: **%d** finding(s)" % dfm_info["width"],
            "- drill / annular ring: **%d** finding(s), %d pad(s) unresolved (unit inference failed)"
            % (dfm_info.get("drill_findings", 0), dfm_info["drill_unresolved"]),
            "",
        ]
    fp_info = s.get("footprints")
    if fp_info:
        lines += [
            "## Footprint audit",
            "",
            "parts with review flags: %s" % (", ".join(fp_info["flagged"]) or "none"),
            "",
        ]
    fab_info = s.get("fabrication")
    if fab_info:
        lines += [
            "## Fabrication manifest",
            "",
            "%d tracks, %.1f mil of copper, %d nets, %d pads; single-pad nets **%d**."
            % (fab_info["tracks"], fab_info["length_mil"], fab_info["nets"],
               fab_info["pads"], fab_info["orphans"]),
            "Gerber / Excellon / BOM / CPL export: **NOT RUN** (needs the EDA execution layer).",
            "",
        ]
    lines += [
        "## Plan vs board rules",
        "",
        "**%s**" % s["plan_lint"]["verdict"],
    ]
    for row in s["plan_lint"]["failing"]:
        lines.append("* %s: %s" % (row["check"], row["detail"]))
    lines += [
        "",
        "## Deliverable",
        "",
        "**%s** - %s" % ("YES" if s["deliverable"] else "NO",
                         "gate and board rules both pass" if s["deliverable"]
                         else "a red gate or a board-rule failure must be resolved first; "
                              "the delivery guard refuses to write to a live board"),
        "",
    ]
    if not s.get("skew_target_met", True):
        # Bus skew lives outside the DRC gate (it is a design target, not a clearance rule), so
        # it has to be named here or a reader will believe the failing list is complete.
        skew_now = s.get("skew") or {}
        if not skew_now:
            # A board with no bus groups has nothing to match; saying "above target ({})" would be a
            # nonsense verdict on a second board with no CAM/LCD/SD groups (GAPS D1, HANDOFF §168).
            lines += ["This board defines **no bus groups** (CAM/LCD/SD), so there is no length matching "
                      "target to report.", ""]
        else:
            lines += ["Bus skew is **above its <50 mil target** (%s) - a pinout decision, not "
                      "something the router can fix." % (skew_now,), ""]
    lines += ["_Spacing groups inspected: %d._" % (group_count or 0), "",]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--profile", default="strict-via-thin", choices=sorted(rep.PROFILES),
                    help="strict-via-thin is the deliverable-grade point (5 mil grid, ~40 min);"
                         " thin-10mil is the fast one (~6-14 min, one real short)")
    ap.add_argument("--stackup", type=int, default=4)
    ap.add_argument("--candidate", choices=sorted(candidates.CANDIDATES),
                    help="build this named candidate (board change + recipe) first")
    a = ap.parse_args()

    s = run(a.dump, a.place, a.out_dir, a.profile, a.stackup, a.candidate)
    print(open(os.path.join(a.out_dir, "report.md"), encoding="utf-8").read())
    print("summary -> %s" % os.path.join(a.out_dir, "summary.json"))
    return 0 if s["deliverable"] else 2


if __name__ == "__main__":
    sys.exit(main())
