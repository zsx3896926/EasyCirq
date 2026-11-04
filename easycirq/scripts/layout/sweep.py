#!/usr/bin/env python3
"""Batch runner: parallel evaluation, a result cache, and a check that a cheap screen can be trusted.

This is the tool the RetroCam effort was missing: a 4–5 minute screen and a 20–45 minute delivery-grade run
were executed one at a time, so most of the wall clock was waiting.  Three things fix that:

  * **parallel** - the router is deterministic, so N configurations can run in N processes;
  * **cache** - keyed on (dump, placement, profile, iterations), so re-running after a doc change is free;
  * **calibration** - a cheap screen may be used to *rank* configurations only if its ranking agrees with
    the delivery grade.  Never again compare a 25-pass number with a 70-pass record (HANDOFF §148).

Usage
-----
    python easycirq/scripts/layout/sweep.py --dump d.json --place p.json \
        --candidates frontier-g,frontier-h --iters 25 --jobs 4
    python easycirq/scripts/layout/sweep.py ... --calibrate 70        # rank agreement between --iters and 70
"""
import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import candidates as _candidates  # noqa: E402
import normalise  # noqa: E402

CACHE_DIR = os.path.join(HERE, ".sweep-cache")
DB_PATH = os.path.join(HERE, ".bench", "results.sqlite")


def record(results, db_path=DB_PATH):
    """Append every evaluated configuration to a small SQLite table.

    The cache answers "give me this result again"; this answers "what have we measured, and how long did it
    take" - the question that used to require re-running things (HANDOFF §184).
    """
    import sqlite3
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS runs (
            key TEXT, candidate TEXT, profile TEXT, iters INTEGER, seconds REAL,
            clearance INTEGER, cam REAL, lcd REAL, sd REAL, l1 REAL, created TEXT,
            PRIMARY KEY (key))""")
        for r in results:
            key = _key(*r["config"])
            k = r["kpi"]
            con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                        (key, r["config"][2] or "-", r["config"][3], r["config"][4],
                         r.get("seconds") or 0.0, k.get("clearance_violations"),
                         r["skew"].get("CAM_D"), r["skew"].get("LCD_"), r["skew"].get("SD_"),
                         float((r.get("layer_share") or {}).get("1", 0.0))))
        con.commit()
    finally:
        con.close()


def report(db_path=DB_PATH, limit=15):
    """Last N stored runs as a markdown table."""
    import sqlite3
    if not os.path.exists(db_path):
        print("no result database yet (%s)" % db_path)
        return []
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("""SELECT candidate, profile, iters, seconds, clearance, cam, l1, created
                              FROM runs ORDER BY created DESC, candidate LIMIT ?""",
                           (limit,)).fetchall()
    finally:
        con.close()
    print("| candidate | profile | iters | secs | clearance | CAM | L1 | when |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %d | %.1f | %s | %s | %s | %s |" % r)
    return rows


def _key(dump_path, place_path, candidate, profile, iters):
    h = hashlib.sha256()
    for path in (dump_path, place_path):
        with open(path, "rb") as f:
            h.update(f.read())
    h.update(("%s|%s|%d" % (candidate or "-", profile, iters)).encode())
    return h.hexdigest()[:20]


def _evaluate_one(args):
    """One configuration -> KPI dict.  Runs inside a worker process, so it rebuilds everything."""
    dump_path, place_path, candidate, profile, iters = args
    import reproduce as rep
    import grid_experiment

    # A "coarse:<profile>" pseudo-profile routes on a 10 mil grid (the cheap screen) while keeping the
    # named profile's other knobs.  It is derived here, not registered in PROFILES, so worker processes
    # (spawned fresh on Windows) can reproduce it from the name alone (HANDOFF §185).
    base = profile.split(":", 1)[1] if profile.startswith("coarse:") else profile
    cfg = dict(rep.PROFILES[base])
    if profile.startswith("coarse:"):
        cfg["grid"] = 10.0
    cfg["iters"] = iters
    if candidate:
        over = _candidates.constants_for(candidate)
        if over:
            cfg["constants"] = {**cfg.get("constants", {}), **over}
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(float(cfg.get("grid") or 10), constants=cfg.get("constants"))

    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        place = json.load(f)
    if candidate:
        dump, place, _prov = _candidates.build(candidate, dump, place)
    board = rep.ec.Board(dump)
    rep.ec.apply_placement(board, place)
    _t0 = time.time()
    routed, fails = rep._route(board, cfg)
    _seconds = round(time.time() - _t0, 1)
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    q = rep.ec.quality_metrics(plan)
    per = q.get("layer_length_mil") or {}
    total = sum(per.values()) or 1.0
    return {"gate": {k: kpi.get(k) for k in ("unrouted_legs", "congestion_cells",
                                            "clearance_violations", "nets_unconnected",
                                            "pad_layer_gaps", "pour_islands")},
            "skew": kpi.get("bus_length_spread_mil") or {},
            "layer_share": {str(k): round(100.0 * v / total, 1) for k, v in per.items()},
            "diagonal_ratio": q.get("diagonal_ratio"),
            "tracks": len(plan.get("tracks") or []), "vias": len(plan.get("vias") or []),
            "seconds": _seconds}


def evaluate(configs, jobs=4, use_cache=True, cache_dir=CACHE_DIR, progress=False):
    """Evaluate [(dump, place, candidate, profile, iters)] with a cache and a process pool."""
    os.makedirs(cache_dir, exist_ok=True) if use_cache else None
    results, todo, keys = {}, [], {}
    for cfg in configs:
        k = _key(*cfg)
        keys[cfg] = k
        path = os.path.join(cache_dir, k + ".json")
        if use_cache and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                results[cfg] = json.load(f)
        else:
            todo.append((cfg, path))

    if todo:
        payloads = [c for c, _p in todo]
        if jobs <= 1:
            # single job: run inline.  It also keeps the module importable from a test harness that
            # loads this file under another name (worker pickling would fail there).
            produced = [_evaluate_one(p) for p in payloads]
        else:
            from concurrent.futures import as_completed
            produced = [None] * len(payloads)
            with ProcessPoolExecutor(max_workers=jobs) as pool:
                futures = {pool.submit(_evaluate_one, p): i for i, p in enumerate(payloads)}
                for done, fut in enumerate(as_completed(futures), start=1):
                    i = futures[fut]
                    produced[i] = fut.result()
                    if progress:
                        c = payloads[i]
                        print("  [%d/%d] %s @ %d iters done (clearance %s)"
                              % (done, len(payloads), c[2] or "-", c[4],
                                 produced[i]["gate"]["clearance_violations"], ), flush=True)
        for (cfg, path), res in zip(todo, produced):
            results[cfg] = res
            if use_cache:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(res, f)

    rows = []
    for cfg in configs:
        res = results[cfg]
        rows.append({"config": cfg, "kpi": res["gate"], "skew": res["skew"],
                     "layer_share": res.get("layer_share", {}),
                     "diagonal_ratio": res.get("diagonal_ratio"),
                     "seconds": res.get("seconds"),
                     "cached": cfg in keys and not any(cfg == c for c, _p in todo)})
    return rows


def spearman(a, b):
    """Rank correlation of two score lists (no ties assumed beyond simple average ranks)."""
    if len(a) != len(b) or len(a) < 2:
        return 1.0
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    den = (sum((x - mean_a) ** 2 for x in ra) * sum((y - mean_b) ** 2 for y in rb)) ** 0.5
    return 0.0 if den == 0 else num / den


def pareto(rows, clearance_key="clearance_violations"):
    """Non-dominated configurations for (clearance, CAM skew) - lower is better for both.

    Rule ④ of the post-mortem: do not sweep fifteen middle values, keep the extremes and the true
    trade-offs.  This marks which rows nothing else beats on both axes at once.
    """
    def score(r):
        return (float(r["kpi"].get(clearance_key) or 0), float(r["skew"].get("CAM_D") or 0.0))

    marked = []
    for i, r in enumerate(rows):
        ci, si = score(r)
        dominated = False
        for j, other in enumerate(rows):
            if i == j:
                continue
            cj, sj = score(other)
            if cj <= ci and sj <= si and (cj < ci or sj < si):
                dominated = True
                break
        marked.append((r, not dominated))
    return marked


def calibrate(fast_rows, slow_rows, threshold=0.8):
    """(ok, rho, detail) - may the cheap screen be used to RANK these configurations?"""
    fast = [r["kpi"]["clearance_violations"] or 0 for r in fast_rows]
    slow = [r["kpi"]["clearance_violations"] or 0 for r in slow_rows]
    rho_c = spearman(fast, slow)
    fast_s = [(r["skew"].get("CAM_D") or 0.0) for r in fast_rows]
    slow_s = [(r["skew"].get("CAM_D") or 0.0) for r in slow_rows]
    rho_s = spearman(fast_s, slow_s)
    ok = rho_c >= threshold and rho_s >= threshold
    detail = ("clearance rho %.2f, CAM rho %.2f (threshold %.2f)" % (rho_c, rho_s, threshold))
    return ok, min(rho_c, rho_s), detail


def write_block(path, block):
    """Replace the generated block in a markdown file, or append it when the markers are absent."""
    head, sep, tail = "<!-- sweep:start -->", "<!-- sweep:end -->", None
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if head in text and sep in text:
        before = text.split(head)[0]
        after = text.split(sep, 1)[1]
        text = before + block + after
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def rank_top(rows, top):
    """Order rows by the documented rule (clearance, then CAM skew) and keep the best `top`."""
    def rank_key(r):
        return (int(r["kpi"].get("clearance_violations") or 0), float(r["skew"].get("CAM_D") or 0.0))
    ordered = sorted(rows, key=rank_key)
    return ordered, ordered[:max(1, top)]


def two_phase(configs, jobs, fast_iters, slow_iters, top, no_cache=False, progress=False,
              coarse_grid=False):
    """Run a coarse screen over every configuration, then the delivery grade only on the best few.

    This is the "two-phase grid" of the speed plan expressed where it is safe: on the *protocol* rather
    than inside the router.  Calibration (§178: clearance rho 0.80, CAM rho 1.00) is what makes the coarse
    ranking trustworthy; the delivery grade is still what gets quoted.
    """
    # Same grid for phase 1 unless the caller insists: the 25-vs-70 pass calibration (§178) does NOT
    # transfer to a coarser grid - a 10 mil screen ranked these four candidates in a different order than
    # the 5 mil delivery run (frontier-g first instead of frontier-i/j), which is exactly why the coarse
    # grid is opt-in and warned about (HANDOFF §185).
    phase1_profile = (lambda name: "coarse:" + name) if coarse_grid else (lambda name: name)
    coarse = [(c[0], c[1], c[2], phase1_profile(c[3]), fast_iters) for c in configs]
    t0 = time.time()
    phase1 = evaluate(coarse, jobs, not no_cache, progress=progress)
    t1 = time.time() - t0
    ordered, keep = rank_top(phase1, top)
    names = [r["config"][2] for r in keep]
    print("phase 1 (%s, %d passes, %.0fs): %s" % (
        "coarse 10 mil grid - RANKING NOT CALIBRATED" if coarse_grid else "same grid, fewer passes",
        fast_iters, t1, ", ".join("%s c=%s" % (r["config"][2], r["kpi"]["clearance_violations"])
                                  for r in ordered)))
    t2 = time.time()
    slow_cfg = [(c[0], c[1], c[2], c[3], slow_iters) for c in configs if c[2] in names]
    phase2 = evaluate(slow_cfg, jobs, not no_cache, progress=progress)
    t3 = time.time() - t2
    print("phase 2 (delivery grade, %d passes, %.0fs): %s" % (
        slow_iters, t3, ", ".join("%s c=%s" % (r["config"][2], r["kpi"]["clearance_violations"])
                                  for r in phase2)))
    print("\ntotal two-phase: %.0fs  (running every configuration at the delivery grade would be more)"
          % (t1 + t3))
    return phase2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="board dump (not needed with --db-report)")
    ap.add_argument("--place", help="placement (not needed with --db-report)")
    ap.add_argument("--candidates", help="comma separated candidate names (default: all active)")
    ap.add_argument("--profile", default="strict-via-thin")
    ap.add_argument("--iters", type=int, default=25)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--calibrate", type=int, metavar="ITERS",
                    help="also run at ITERS and report the rank agreement with --iters")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--progress", action="store_true", help="print each configuration as it finishes")
    ap.add_argument("--brief", action="store_true", help="one line per configuration, no table")
    ap.add_argument("--no-db", action="store_true", help="do not append to the result database")
    ap.add_argument("--db-report", type=int, metavar="N", help="print the last N stored runs and exit")
    ap.add_argument("--two-phase", action="store_true",
                    help="coarse screen on every configuration, then the delivery grade on the best few")
    ap.add_argument("--fast-grid-iters", type=int, default=8, metavar="N",
                    help="iterations for the coarse (10 mil) phase")
    ap.add_argument("--top", type=int, default=2, help="how many configurations survive the coarse phase")
    ap.add_argument("--coarse-grid", action="store_true",
                    help="phase 1 on a 10 mil grid - WARNING: its ranking is NOT calibrated against the "
                         "delivery grade (measured to disagree, HANDOFF §185); same-grid screening is the "
                         "calibrated default")
    ap.add_argument("--pareto", action="store_true", help="mark the non-dominated points")
    ap.add_argument("--write-table", metavar="PATH",
                    help="also write the KPI table (between <!-- sweep:start/end --> markers) into PATH")
    a = ap.parse_args()

    if a.db_report:
        report(limit=a.db_report)
        return 0

    if not a.dump or not a.place:
        raise SystemExit("--dump and --place are required (unless --db-report)")

    if a.candidates:
        names = [n for n in a.candidates.split(",") if n]
    else:
        names = [n for n, s in _candidates.CANDIDATES.items() if not s.get("deprecated_illegal")]
    configs = [(a.dump, a.place, n, a.profile, a.iters) for n in names]

    if a.two_phase:
        phase2 = two_phase(configs, a.jobs, a.fast_grid_iters, a.iters, a.top,
                           no_cache=a.no_cache, progress=a.progress, coarse_grid=a.coarse_grid)
        if not a.no_db:
            try:
                record(phase2)
            except Exception as exc:
                print("(result database not updated: %s)" % exc)
        print("| candidate | clearance | CAM |")
        print("|---|---|---|")
        for r in phase2:
            print("| %s | %s | %.1f |" % (r["config"][2], r["kpi"]["clearance_violations"],
                                          r["skew"].get("CAM_D", 0.0)))
        return 0

    t0 = time.time()
    rows = evaluate(configs, a.jobs, not a.no_cache, progress=a.progress)
    elapsed = time.time() - t0
    if a.brief:
        for r in rows:
            k = r["kpi"]
            print("%-16s clearance %-5s CAM %7.1f LCD %5.1f SD %4.1f L1 %4.1f%%%s" % (
                r["config"][2], k["clearance_violations"], r["skew"].get("CAM_D", 0.0),
                r["skew"].get("LCD_", 0.0), r["skew"].get("SD_", 0.0),
                float(r["layer_share"].get("1", 0.0)), "  (cached)" if r["cached"] else ""))
    else:
        print("| candidate | clearance | CAM | LCD | SD | L1 | cached |")
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            k = r["kpi"]
            print("| %s | %s | %.1f | %.1f | %.1f | %.1f%% | %s |" % (
                r["config"][2], k["clearance_violations"], r["skew"].get("CAM_D", 0.0),
                r["skew"].get("LCD_", 0.0), r["skew"].get("SD_", 0.0),
                float(r["layer_share"].get("1", 0.0)), "yes" if r["cached"] else "no"))

    if not a.no_db:
        try:
            record(rows)
        except Exception as exc:                        # a database problem must never lose a result
            print("(result database not updated: %s)" % exc)
    if a.pareto:
        marked = pareto(rows)
        print("\nnon-dominated points (clearance vs CAM, lower is better): %s" % (
            ", ".join(r["config"][2] for r, keep in marked if keep) or "none"))
    print("\n%d configuration(s) at %d passes in %.1fs (%d jobs)" % (
        len(rows), a.iters, elapsed, a.jobs))

    if a.write_table:
        block = ["<!-- sweep:start -->",
                 "| candidate | clearance | CAM | LCD | SD | L1 |",
                 "|---|---|---|---|---|---|"]
        for r in rows:
            k = r["kpi"]
            block.append("| %s | %s | %.1f | %.1f | %.1f | %.1f%% |" % (
                r["config"][2], k["clearance_violations"], r["skew"].get("CAM_D", 0.0),
                r["skew"].get("LCD_", 0.0), r["skew"].get("SD_", 0.0),
                float(r["layer_share"].get("1", 0.0))))
        block.append("<!-- sweep:end -->")
        write_block(a.write_table, "\n".join(block))

    if a.calibrate:
        slow_cfg = [(a.dump, a.place, n, a.profile, a.calibrate) for n in names]
        slow_rows = evaluate(slow_cfg, a.jobs, not a.no_cache)
        ok, rho, detail = calibrate(rows, slow_rows)
        print("\ncalibration vs %d passes: %s -> %s" % (
            a.calibrate, detail,
            "the cheap screen MAY be used for ranking" if ok
            else "DO NOT rank configurations on the cheap screen"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
