#!/usr/bin/env python3
"""Regression gate for the measured candidates (GAPS G5).

The effort's hard-won numbers are easy to lose: moving J3 by 5 mil once took CAM from 80 to 324, and a
recipe reordering silently produced a different board (§113).  So every candidate carries the KPI record
it was measured with, and this tool re-measures it and fails on any regression.

  * gate items (unrouted / congestion / unconnected / pad gaps / islands): must stay at their record
  * clearance: may not exceed the record (a small tolerance is allowed for screen runs)
  * bus skew per group: may not exceed the record by more than `--skew-tol`, and the groups that are
    already inside the 50 mil target must stay inside it

`--iters 25` is the fast screen used during tuning; `--iters 70` is the delivery-grade run.  Both are
honest: the tolerance is printed so nobody has to guess what "no regression" meant.

Usage
-----
    python easycirq/scripts/layout/regress.py --dump dump2.json --place ec-placed.json \
        [--candidate frontier-d] [--iters 25] [--profile strict-via-thin]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import candidates  # noqa: E402

def _refuse_deprecated(name, allow=False):
    """A deprecated candidate is an ILLEGAL placement (§143-§146 audit).  Refuse it by default so no one
    measures against a board whose parts overlap."""
    spec = candidates.CANDIDATES.get(name) or {}
    if spec.get("deprecated_illegal") and not allow:
        raise SystemExit(
            "candidate %r is DEPRECATED (illegal placement, see HANDOFF §143-§146). "
            "Use frontier-g, or pass --allow-illegal if you really mean to re-measure it." % name)
    return spec

import grid_experiment  # noqa: E402
import reproduce as rep  # noqa: E402

GATE_KEYS = ("unrouted_legs", "congestion_cells", "nets_unconnected",
             "pad_layer_gaps", "pour_islands")
SKEW_TARGET = 50.0


def compare(recorded, measured, clearance_tol=0.0, skew_tol=0.0, skew_target=SKEW_TARGET,
            diagonal_tol=0.005, layer_tol=1.0):
    """Pure comparison so the rule can be tested without routing anything.

    Returns (ok, rows) where each row is (name, recorded, measured, verdict, note).
    """
    rows = []
    ok = True
    for key in GATE_KEYS:
        rec = recorded.get(key)
        got = measured.get(key)
        if rec is None or got is None:
            continue
        good = got <= rec
        ok = ok and good
        rows.append((key, rec, got, "OK" if good else "REGRESSED", "gate item must not rise"))
    rec_c = recorded.get("clearance_violations")
    got_c = measured.get("clearance_violations")
    if rec_c is not None and got_c is not None:
        limit = rec_c + max(clearance_tol, 0.0)
        good = got_c <= limit
        ok = ok and good
        rows.append(("clearance_violations", rec_c, got_c, "OK" if good else "REGRESSED",
                     "limit %.1f" % limit))
    # shape metrics (GAPS G6): the L1 share may not grow and the 45-degree share may not fall.
    # They are optional because a record may not carry them; when present they are enforced.
    for key, better in (("diagonal_ratio", "higher"), ("layer_share", "lower_l1")):
        rec_v = recorded.get(key)
        got_v = measured.get(key)
        if rec_v is None or got_v is None:
            continue
        if key == "diagonal_ratio":
            limit = rec_v - diagonal_tol
            good = got_v >= limit
            note = "may not fall below %.3f" % limit
        else:
            rec_l1 = float(rec_v.get("1", 0.0))
            got_l1 = float(got_v.get("1", 0.0))
            limit = rec_l1 + layer_tol
            good = got_l1 <= limit
            note = "L1 share may not exceed %.1f%%" % limit
            rec_v, got_v = rec_l1, got_l1
        ok = ok and good
        rows.append((key, rec_v, got_v, "OK" if good else "REGRESSED", note))

    rec_s = recorded.get("bus_length_spread_mil") or {}
    got_s = measured.get("bus_length_spread_mil") or {}
    for group in sorted(rec_s):
        rec = rec_s[group]
        got = got_s.get(group)
        if got is None:
            continue
        limit = rec + skew_tol
        # a group that was inside the target must stay inside it, even if the record was loose
        if rec <= skew_target:
            limit = min(limit, skew_target + skew_tol)
        good = got <= limit
        ok = ok and good
        rows.append(("skew %s" % group, rec, got, "OK" if good else "REGRESSED",
                     "limit %.1f" % limit))
    return ok, rows


def measure(name, dump_path, place_path, profile, iters, out_dir=None):
    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        place = json.load(f)
    d, p, _prov = candidates.build(name, dump, place)
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    overrides = candidates.constants_for(name)
    if overrides:
        cfg["constants"] = {**cfg.get("constants", {}), **overrides}
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(float(cfg.get("grid") or 10),
                                        constants=cfg.get("constants"))
    board = rep.ec.Board(d)
    rep.ec.apply_placement(board, p)
    routed, fails = rep._route(board, cfg)
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    q = rep.ec.quality_metrics(plan)
    per = q.get("layer_length_mil") or {}
    total = sum(per.values()) or 1.0
    out = {k: kpi.get(k) for k in GATE_KEYS + ("clearance_violations", "bus_length_spread_mil")}
    out["diagonal_ratio"] = q.get("diagonal_ratio")
    out["layer_share"] = {str(k): round(100.0 * v / total, 1) for k, v in per.items()}
    return out, plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--candidate", default="frontier-g", choices=sorted(candidates.CANDIDATES),
                    help="frontier-g is the only active (legal) candidate; see GAPS G12")
    ap.add_argument("--allow-illegal", action="store_true",
                    help="re-measure a deprecated candidate anyway (its placement overlaps)")
    ap.add_argument("--profile", default="strict-via-thin", choices=sorted(rep.PROFILES))
    ap.add_argument("--iters", type=int, default=25,
                    help="25 = fast screen used while tuning, 70 = delivery grade")
    ap.add_argument("--clearance-tol", type=float, default=0.0)
    ap.add_argument("--skew-tol", type=float, default=0.0)
    ap.add_argument("--diagonal-tol", type=float, default=0.005,
                    help="allowed fall in the 45-degree share")
    ap.add_argument("--layer-tol", type=float, default=1.0,
                    help="allowed rise of the L1 layer share, percentage points")
    a = ap.parse_args()

    _refuse_deprecated(a.candidate, a.allow_illegal)
    spec = candidates.CANDIDATES[a.candidate]
    recorded = spec["measured"]
    if a.iters != 70 and spec.get("measured_screen"):
        screen = spec["measured_screen"]
        recorded = {**recorded, **screen}
        # only enforce the shape metrics that were actually recorded at this iteration count -
        # otherwise the 70-pass numbers would be compared against a 25-pass run
        for key in ("diagonal_ratio", "layer_share"):
            if key not in screen:
                recorded.pop(key, None)
    measured, _plan = measure(a.candidate, a.dump, a.place, a.profile, a.iters)
    ok, rows = compare(recorded, measured, a.clearance_tol, a.skew_tol,
                       diagonal_tol=a.diagonal_tol, layer_tol=a.layer_tol)

    print("regression check: candidate %s (%s), %d passes, profile %s"
          % (a.candidate, candidates.CANDIDATES[a.candidate]["section"], a.iters, a.profile))
    print("| KPI | recorded | measured | verdict | rule |")
    print("|---|---|---|---|---|")
    for name, rec, got, verdict, note in rows:
        print("| %s | %s | %s | %s | %s |" % (name, rec, got, verdict, note))
    print("\n%s" % ("PASS - no regression" if ok else "FAIL - a measured number regressed"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
