#!/usr/bin/env python3
"""Benchmark harness: time AND KPI fingerprint for a fixed set of boards (step 1 of the speed plan).

Optimising a router without a baseline is how you get a 1.4x "improvement" that quietly changed the plan.
This harness fixes three boards and two profiles, records wall time plus a KPI fingerprint for each, and can
dump a `cProfile` breakdown so the next optimisation is aimed at the real hotspot instead of a guess.

Fingerprint = the six gate items + bus skew + tracks/vias/total length.  Any change that alters it is not a
speed-up, it is a different result - the comparison is refused, not averaged.

Usage
-----
    python easycirq/scripts/layout/bench.py                      # baseline table (default 5 iterations per spot)
    python easycirq/scripts/layout/bench.py --iters 25 --write   # slower, writes .bench/baseline.json
    python easycirq/scripts/layout/bench.py --profile-call       # cProfile the heaviest spot and print the top costs
    python easycirq/scripts/layout/bench.py --compare            # compare the current run against the stored baseline
"""
import argparse
import cProfile
import io
import json
import os
import pstats
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORKSPACE = os.path.dirname(REPO)
sys.path.insert(0, HERE)

import candidates  # noqa: E402
import ec_layout as ec  # noqa: E402
import grid_experiment  # noqa: E402
import normalise  # noqa: E402
import reproduce as rep  # noqa: E402
import selftest  # noqa: E402

BENCH_DIR = os.path.join(HERE, ".bench")
BASELINE = os.path.join(BENCH_DIR, "baseline.json")

# 板子数据位置。搬进 EasyCirq 后不能再假设它在 <repo>/../../retrocam-02。
# 查找顺序：
#   1. $EASYCIRQ_LAYOUT_BOARD  —— 指到含 dump2.json / ec-placed.json 的目录
#   2. <工具链>/fixtures        —— 随包夹具（RetroCam-02 最小集）
#   3. <workspace>/retrocam-02  —— 旧布局，兼容从 hds-verifier 直接跑
# 都找不到时 retrocam 两项**跳过并明说 NOT RUN**，不伪造数字。
FIXTURES = os.path.join(HERE, "fixtures")


def _resolve_board():
    env = os.environ.get("EASYCIRQ_LAYOUT_BOARD", "").strip()
    if env:
        d = env
        if os.path.isdir(os.path.join(d, "pcb")):
            d = os.path.join(d, "pcb")
        return (os.path.join(d, "dump2.json"),
                os.path.join(d, "ec-placed.json"))
    if os.path.isfile(os.path.join(FIXTURES, "dump2.json")):
        return (os.path.join(FIXTURES, "dump2.json"),
                os.path.join(FIXTURES, "ec-placed.json"))
    legacy = os.path.join(WORKSPACE, "retrocam-02", "pcb")
    return (os.path.join(legacy, "dump2.json"),
            os.path.join(legacy, "offline", "ec-placed.json"))


REAL_DUMP, REAL_PLACE = _resolve_board()


def _write_temp(tmp_dir, name, obj):
    path = os.path.join(tmp_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return path


NOT_RUN = []


def spots(tmp_dir):
    """(label, dump_path, place_path, candidate, profile) - the fixed set the bench compares.

    输入缺失的 spot 进 `NOT_RUN` 并在结果后打印 —— 不许静默少一行，
    否则对比表看起来是完整的。
    """
    del NOT_RUN[:]
    out = []
    if os.path.exists(REAL_DUMP) and os.path.exists(REAL_PLACE):
        out.append(("retrocam/frontier-i", REAL_DUMP, REAL_PLACE, "frontier-i", "strict-via-thin"))
        out.append(("retrocam/frontier-i-fast", REAL_DUMP, REAL_PLACE, "frontier-i", "thin-10mil"))
    else:
        NOT_RUN.append(("retrocam/frontier-i", "板子输入缺失: %s" % REAL_DUMP))
        NOT_RUN.append(("retrocam/frontier-i-fast", "板子输入缺失: %s" % REAL_DUMP))
    # 第二块板：优先随包夹具，其次旧的 worktree 路径。
    second = os.path.join(FIXTURES, "second-board.json")
    if not os.path.exists(second):
        second = os.path.join(WORKSPACE, "hardware-design-skill", ".agents", "worktrees", "feat",
                              "pcb-placement-round6", "docs", "evidence",
                              "round7-baseline-2026-10-24", "pcb-dump.json")
    if os.path.exists(second):
        with open(second, encoding="utf-8") as f:
            dump = json.load(f)
        r = dump.get("result") or dump
        place = {c["designator"]: {"x": c["x"], "y": c["y"], "rotation": c.get("rotation", 0)}
                 for c in r.get("components") or []}
        d_path = _write_temp(tmp_dir, "second-dump.json", dump)
        p_path = _write_temp(tmp_dir, "second-place.json", place)
        out.append(("second-2layer", d_path, p_path, None, "two-layer"))
    else:
        NOT_RUN.append(("second-2layer", "第二块板缺失: %s" % second))
    out.append(("selftest", _write_temp(tmp_dir, "st-dump.json", selftest.make_dump()),
                _write_temp(tmp_dir, "st-place.json", selftest.make_place()), None, "strict-via-thin"))
    return out


def run_spot(label, dump_path, place_path, candidate, profile, iters):
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    if candidate:
        over = candidates.constants_for(candidate)
        if over:
            cfg["constants"] = {**cfg.get("constants", {}), **over}
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(float(cfg.get("grid") or 10), constants=cfg.get("constants"))

    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        place = json.load(f)
    if candidate:
        dump, place, _prov = candidates.build(candidate, dump, place)
    # a capture may live in a negative coordinate frame; shifting it is what rep.run does too (§168)
    dump, place, _offset = normalise.apply(dump, place)

    if os.environ.get("BENCH_DEBUG"):
        print("  [spot] profile=%s iters=%d grid_in_cfg=%r ec.GRID=%s nets_in_dump=%d"
              % (profile, iters, cfg.get("grid"), getattr(rep.ec, "GRID", "?"),
                 len(dump.get("result", dump).get("components") or [])))
    t0 = time.time()
    board = rep.ec.Board(dump)
    rep.ec.apply_placement(board, place)
    routed, fails = rep._route(board, cfg)
    if os.environ.get("BENCH_DEBUG"):
        print("  [spot] board.nets=%d routed=%d legs_failed=%d" % (len(board.nets), len(routed), len(fails)))
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    elapsed = time.time() - t0

    q = rep.ec.quality_metrics(plan)
    return {
        "label": label, "profile": profile, "iters": iters, "seconds": round(elapsed, 1),
        "fingerprint": {
            "gate": {k: kpi.get(k) for k in ("unrouted_legs", "congestion_cells",
                                             "clearance_violations", "nets_unconnected",
                                             "pad_layer_gaps", "pour_islands")},
            "skew": kpi.get("bus_length_spread_mil") or {},
            "tracks": len(plan.get("tracks") or []),
            "vias": len(plan.get("vias") or []),
            "total_length_mil": round(float(q.get("total_length_mil") or 0.0), 1),
        },
    }


def _run_isolated(label, dump_path, place_path, candidate, profile, iters):
    """Run one spot in a fresh process and return its result dict.

    The router keeps module-level state (grid, constants); reusing it across spots silently produced an
    empty plan for the second board.  A process per spot is also how a batch run should behave.
    """
    import subprocess
    cmd = [sys.executable, os.path.abspath(__file__), "--one", json.dumps(
        {"label": label, "dump": dump_path, "place": place_path,
         "candidate": candidate, "profile": profile, "iters": iters})]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    line = [l for l in proc.stdout.splitlines() if l.startswith("BENCH_JSON ")]
    if not line:
        raise SystemExit("spot %r failed:\n%s\n%s" % (label, proc.stdout[-1500:], proc.stderr[-1500:]))
    return json.loads(line[0][len("BENCH_JSON "):])


def compare(current, baseline, tolerance=0.0):
    """(ok, rows) - the KPI fingerprint must be identical; only `seconds` may change."""
    rows, ok = [], True
    for cur in current:
        base = next((b for b in baseline if b["label"] == cur["label"]), None)
        if base is None:
            rows.append((cur["label"], "not in baseline", "skip"))
            continue
        same = cur["fingerprint"] == base["fingerprint"]
        ok = ok and same
        speed = base["seconds"] / cur["seconds"] if cur["seconds"] else 0.0
        rows.append((cur["label"], "%.1fs vs %.1fs (%.2fx)" % (base["seconds"], cur["seconds"], speed),
                     "same KPI" if same else "**KPI CHANGED**"))
    return ok, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=5)
    ap.add_argument("--write", action="store_true", help="store this run as the baseline")
    ap.add_argument("--compare", action="store_true", help="compare against the stored baseline")
    ap.add_argument("--profile-call", action="store_true", help="cProfile the last/heaviest spot")
    ap.add_argument("--one", help="internal: run a single spot described by JSON and print it")
    ap.add_argument("--isolated", action="store_true", default=True,
                    help="run each spot in its own process (default; keeps module state from leaking)")
    a = ap.parse_args()

    if a.one:
        spec = json.loads(a.one)
        res = run_spot(spec["label"], spec["dump"], spec["place"], spec["candidate"],
                       spec["profile"], spec["iters"])
        print("BENCH_JSON " + json.dumps(res))
        return 0

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="bench-")
    os.makedirs(BENCH_DIR, exist_ok=True)
    rows = []
    for label, d, p, cand, prof in spots(tmp_dir):
        res = _run_isolated(label, d, p, cand, prof, a.iters)
        rows.append(res)
        print("%-26s %-16s %4d iters  %7.1fs  tracks %4d  clearance %4s  CAM %s" % (
            label, prof, a.iters, res["seconds"], res["fingerprint"]["tracks"],
            res["fingerprint"]["gate"]["clearance_violations"],
            res["fingerprint"]["skew"].get("CAM_D", "-")))

    if a.write:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({"iters": a.iters, "rows": rows}, f, indent=1)
        print("\nbaseline written to %s" % BASELINE)

    if a.compare:
        if not os.path.exists(BASELINE):
            print("\nno baseline stored - run with --write first")
            return 1
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)["rows"]
        ok, cmp_rows = compare(rows, base)
        print("\n| spot | time | verdict |")
        print("|---|---|---|")
        for label, detail, verdict in cmp_rows:
            print("| %s | %s | %s |" % (label, detail, verdict))
        print("\n%s" % ("identical KPI fingerprint" if ok else "the KPI fingerprint CHANGED - not a speed-up"))

    if NOT_RUN:
        print()
        print("NOT RUN (inputs missing - these spots were NOT measured):")
        for label, why in NOT_RUN:
            print("  %-26s %s" % (label, why))
        return 0 if ok else 1

    if a.profile_call:
        label, d, p, cand, prof = spots(tmp_dir)[0]
        pr = cProfile.Profile()
        pr.enable()
        run_spot(label, d, p, cand, prof, a.iters)
        pr.disable()
        buf = io.StringIO()
        pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(18)
        print("\ncProfile (cumulative, %s @ %d iters):" % (label, a.iters))
        print("\n".join(buf.getvalue().splitlines()[:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
