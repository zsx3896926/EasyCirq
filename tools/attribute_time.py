#!/usr/bin/env python3
"""归因：网络数翻倍时，时间为什么涨 2.3 倍？

不改一行优化代码。只做一件事：**把多出来的时间拆开**。

三个可能的来源，必须分开：
  A) **腿数**（legs）随网络数线性涨 —— 那是应该的，不算问题
  B) **每条腿的 A* 调用次数**涨（重试变多）—— 说明后布的网被前面的铜挡住
  C) **单次 A* 变慢**（搜索空间变大 / 失败回溯更久）

用法：
    python tools/attribute_time.py --factors 1,2,4
"""
import argparse
import json
import pathlib
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAY = ROOT / "easycirq" / "scripts" / "layout"
sys.path.insert(0, str(LAY))

import candidates  # noqa: E402
import grid_experiment  # noqa: E402
import normalise as norm_mod  # noqa: E402
import reproduce as rep  # noqa: E402
import scale_bench  # noqa: E402


def measure(dump, place, label, profile="strict-via-thin", iters=1):
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    rep.use_grid(cfg.get("grid"))
    ec = grid_experiment.load_module(float(cfg.get("grid") or 10),
                                     constants=cfg.get("constants"))
    rep.ec = ec

    d, p, _ = norm_mod.apply(dump, place)
    board = ec.Board(d)
    ec.apply_placement(board, p)

    stats = {
        "calls": 0, "none": 0, "found": 0,
        "astar_secs": 0.0, "per_call": [],
        "by_net": Counter(), "none_by_net": Counter(),
    }
    real = ec.astar

    def spy(*a, **kw):
        stats["calls"] += 1
        net = kw.get("net")
        stats["by_net"][net] += 1
        t0 = time.perf_counter()
        r = real(*a, **kw)
        dt = time.perf_counter() - t0
        stats["astar_secs"] += dt
        stats["per_call"].append(dt)
        if r is None:
            stats["none"] += 1
            stats["none_by_net"][net] += 1
        else:
            stats["found"] += 1
        return r

    ec.astar = spy
    t0 = time.perf_counter()
    routed, fails = rep._route(board, cfg)
    plan = ec.plan_from(board, routed)
    kpi = ec.report(board, routed, fails, [], plan)
    total = time.perf_counter() - t0
    ec.astar = real

    legs = sum(len(v) if isinstance(v, (list, tuple)) else 1
               for v in (routed or {}).values()) or 0
    per = sorted(stats["per_call"])
    med = per[len(per) // 2] if per else 0.0
    p90 = per[int(len(per) * 0.9)] if per else 0.0

    return {
        "label": label,
        "W": board.w, "H": board.h,
        "nets": len(board.nets),
        "tracks": len(plan.get("tracks") or []),
        "unrouted": kpi.get("unrouted_legs"),
        "total_secs": round(total, 2),
        "astar_secs": round(stats["astar_secs"], 2),
        "astar_share": round(100 * stats["astar_secs"] / max(total, 1e-9), 1),
        "calls": stats["calls"],
        "found": stats["found"],
        "none": stats["none"],
        "calls_per_net": round(stats["calls"] / max(len(board.nets), 1), 2),
        "med_ms": round(med * 1000, 2),
        "p90_ms": round(p90 * 1000, 2),
        "found_ms": round(1000 * stats["astar_secs"] / max(stats["found"], 1), 2),
        "worst_nets": stats["by_net"].most_common(5),
        "worst_fail": stats["none_by_net"].most_common(5),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factors", default="1,2,4")
    ap.add_argument("--profile", default="strict-via-thin")
    ap.add_argument("--iters", type=int, default=1)
    a = ap.parse_args()

    dump = json.loads((LAY / "fixtures" / "dump2.json").read_text(encoding="utf-8"))
    place = json.loads((LAY / "fixtures" / "ec-placed.json").read_text(encoding="utf-8"))

    rows = []
    for k in [int(x) for x in a.factors.split(",") if x.strip()]:
        if k == 1:
            d, p = dump, place
        else:
            d, p = scale_bench.make_tiled(dump, place, k)
        label = "x%d" % k
        print("跑 %s ..." % label, flush=True)
        rows.append(measure(d, p, label, a.profile, a.iters))

    print()
    print("| 档位 | 网络 | A* 调用 | 每网调用 | 失败 | 总耗时 | A* 占比 | "
          "中位 | p90 | 每次成功均耗时 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %d | %d | %s | %d | %ss | %s%% | %sms | %sms | %sms |" % (
            r["label"], r["nets"], r["calls"], r["calls_per_net"], r["none"],
            r["total_secs"], r["astar_share"], r["med_ms"], r["p90_ms"],
            r["found_ms"]))
    print()
    for r in rows:
        print("%s：调用最多的网 %s" % (r["label"], r["worst_nets"]))
        print("%s：失败最多的网 %s" % (r["label"], r["worst_fail"]))

    # 拆解：从 x1 到最大档，时间涨了多少倍，各来源贡献多少
    if len(rows) >= 2:
        base, top = rows[0], rows[-1]
        print()
        print("=== 拆解：%s → %s ===" % (base["label"], top["label"]))
        tf = top["total_secs"] / max(base["total_secs"], 1e-9)
        nf = top["nets"] / max(base["nets"], 1)
        cf = top["calls_per_net"] / max(base["calls_per_net"], 1e-9)
        sf = top["found_ms"] / max(base["found_ms"], 1e-9)
        print("  总耗时 x%.2f；网络 x%.2f；每网调用 x%.2f；单次成功均耗时 x%.2f"
              % (tf, nf, cf, sf))
        print("  三项相乘 = x%.2f（与总耗时 x%.2f 的差来自固定开销）"
              % (nf * cf * sf, tf))


if __name__ == "__main__":
    main()
