#!/usr/bin/env python3
"""Single health check for this toolchain (run this first).

The workflow grew a dozen scripts and four candidates; this is the one command that says whether the
repository is healthy before anything else is attempted:

  1. the layout unit tests pass
  2. every active candidate builds deterministically and produces a LEGAL placement
  3. the recorded measurements are internally consistent (each candidate's record names its section)
  4. the offline calculators run on the default candidate (DFM, footprints, fabrication manifest)
  5. optionally: a real 25-pass routing screen of the default candidate (`--route`)
  6. optionally: the four-candidate comparison (`--all-routes`, ~18 min)

Design notes: no routing runs by default (seconds, not minutes), nothing touches a board, and every
stage prints PASS/FAIL so a partial run is still honest.

Usage
-----
    python easycirq/scripts/layout/verify.py [--route] [--all-routes] [--dump ...] [--place ...]
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # <workspace>/hds-verifier
WORKSPACE = os.path.dirname(REPO)                      # the board lives in the sibling checkout
sys.path.insert(0, HERE)

import candidates  # noqa: E402
import ec_layout as ec  # noqa: E402
import gerber  # noqa: E402
import selftest  # noqa: E402

def _resolve_board():
    """板子数据随包夹具兜底，可用 $EASYCIRQ_LAYOUT_BOARD 覆盖。"""
    env = os.environ.get("EASYCIRQ_LAYOUT_BOARD", "").strip()
    if env:
        d = env
        if os.path.isdir(os.path.join(d, "pcb")):
            d = os.path.join(d, "pcb")
        return (os.path.join(d, "dump2.json"),
                os.path.join(d, "ec-placed.json"))
    fx = os.path.join(HERE, "fixtures")
    if os.path.isfile(os.path.join(fx, "dump2.json")):
        return os.path.join(fx, "dump2.json"), os.path.join(fx, "ec-placed.json")
    legacy = os.path.join(WORKSPACE, "retrocam-02", "pcb")
    return (os.path.join(legacy, "dump2.json"),
            os.path.join(legacy, "offline", "ec-placed.json"))


DEFAULT_DUMP, DEFAULT_PLACE = _resolve_board()


def stage(name):
    print("\n== %s ==" % name)


def run(cmd, cwd=None):
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=DEFAULT_DUMP)
    ap.add_argument("--place", default=DEFAULT_PLACE)
    ap.add_argument("--route", action="store_true", help="also run a 25-pass screen (~5 min)")
    ap.add_argument("--all-routes", action="store_true", help="also compare all candidates (~18 min)")
    ap.add_argument("--iters", type=int, default=25)
    ap.add_argument("--skip-tests", action="store_true",
                    help="skip the unit-test stage (needed when called FROM a unit test)")
    a = ap.parse_args()

    results = []

    def check(name, ok, detail=""):
        results.append((name, ok))
        print("%-46s %s" % (name, "PASS" if ok else "FAIL"))
        if detail and not ok:
            for line in detail.strip().splitlines()[-12:]:
                print("    " + line)

    stage("1. layout unit tests")
    if a.skip_tests:
        print("skipped (--skip-tests)")
    else:
        # 单测随工具链一起搬到了 layout/tests/，cwd 用工具链目录
        rc, out, secs = run([sys.executable, "-m", "pytest", "tests/test_ec_layout.py",
                             "tests/test_bus_order.py", "-q"], cwd=HERE)
        check("layout unit tests (%.0fs)" % secs, rc == 0, out)

    have_inputs = os.path.exists(a.dump) and os.path.exists(a.place)
    if not have_inputs:
        print("board inputs not present; skipping the input-dependent stages")
        return _summary(results)

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    with open(a.place, encoding="utf-8") as f:
        place = json.load(f)

    stage("2. candidates: deterministic build + legal placement")
    active = [n for n, sp in candidates.CANDIDATES.items() if not sp.get("deprecated_illegal")]
    deprecated = [n for n, sp in candidates.CANDIDATES.items() if sp.get("deprecated_illegal")]
    built = {}
    for name in active:
        d1, p1, prov = candidates.build(name, dump, place)
        d2, p2, _ = candidates.build(name, dump, place)
        same = (json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
                and json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True))
        b = ec.Board(d1)
        ec.apply_placement(b, p1)
        ov, outside = ec.n_overlaps(b.comps), ec.n_outside(b.comps, b)
        built[name] = (d1, p1)
        check("%s: idempotent + legal" % name,
              same and ov == 0 and outside == 0,
              "idempotent=%s overlaps=%d outside=%d" % (same, ov, outside))
    print("withdrawn (illegal, refused by regress): %s" % (", ".join(deprecated) or "none"))

    stage("3. recorded measurements are self-describing")
    for name in active:
        spec = candidates.CANDIDATES[name]
        rec = spec.get("measured") or {}
        ok = bool(spec.get("section")) and "clearance_violations" in rec \
            and "bus_length_spread_mil" in rec
        check("%s: record names its section and KPI" % name, ok,
              json.dumps({k: rec.get(k) for k in ("clearance_violations",)}))

    stage("4. offline calculators on the default candidate")
    default = "frontier-g" if "frontier-g" in built else active[0]
    d_def, p_def = built[default]
    tmp_dump = os.path.join(HERE, ".verify-dump.json")
    with open(tmp_dump, "w", encoding="utf-8") as f:
        json.dump(d_def, f)
    for tool in ("dfm.py", "footprints.py", "fabrication.py"):
        rc, out, secs = run([sys.executable, os.path.join(HERE, tool), "--dump", tmp_dump])
        check("%s runs on %s (%.0fs)" % (tool, default, secs), rc == 0, out)
    os.remove(tmp_dump)

    stage("5. self-test board: green gate + manufacturing round trip")
    st = selftest.run(iters=60)
    check("self-test board is fully green", st["gate_pass"] and st["skew_pass"],
          "gate=%s skew=%s failing=%s" % (st["gate_pass"], st["skew"], st["failing"]))
    gdir = os.path.join(st["dir"], "gerber")
    gerber.write(selftest.make_dump(), st["plan"], gdir, layers=2)
    ok, rows = gerber.verify(selftest.make_dump(), st["plan"], gdir, layers=2)
    check("gerber/excellon round trip", ok, "; ".join("%s: %s" % (r[0], r[1]) for r in rows))

    if a.route or a.all_routes:
        stage("5. routing screen")
        targets = active if a.all_routes else [default]
        for name in targets:
            rc, out, secs = run([sys.executable, os.path.join(HERE, "gaps_check.py"),
                                 "--dump", a.dump, "--place", a.place,
                                 "--candidate", name, "--iters", str(a.iters)])
            check("%s: acceptance matrix (%.0fs)" % (name, secs), rc == 0, out)

    if a.all_routes:
        stage("6. all-candidate comparison")
        rc, out, secs = run([sys.executable, os.path.join(HERE, "gaps_check.py"),
                             "--dump", a.dump, "--place", a.place,
                             "--candidate", "all", "--iters", str(a.iters)])
        check("comparison table (%.0fs)" % secs, rc == 0, out)
        print(out.strip().splitlines()[-6:])

    return _summary(results)


def _summary(results):
    bad = [n for n, ok in results if not ok]
    print("\n" + "-" * 60)
    if bad:
        print("verify: %d FAILED (%s)" % (len(bad), ", ".join(bad)))
        print("Note: a failing acceptance matrix is EXPECTED for every current candidate - the two P0\n"
              "targets (clearance 0, CAM < 50) are not met by design, see GAPS.md.")
        return 1
    print("verify: all stages passed (%d checks)" % len(results))
    print("Reminder: passing stages do not make a board deliverable - run gaps_check for the KPI table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
