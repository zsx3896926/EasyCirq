#!/usr/bin/env python3
"""等价性门禁 —— 动性能之前必须先立的那道闸。

# 为什么需要它

`bench --compare` 比的是 **KPI 指纹**。但两个不同的 plan 可以给出同一组 KPI：
KPI 相同不等于走线相同。改内循环（换数据结构、内联、预计算）时，
"数字没变"这句话不够 —— 要证明**产物没变**。

所以这里比的是 plan 的**归一化 SHA256**，和 `emit_apply` 用来拒绝上板的是同一个：
`sha256(json.dumps(normalise(plan), sort_keys=True))`。
出错方向只有一个：plan 变了就红。

# 用法

    python equivalence.py --iters 3 --write      # 记录当前产物指纹
    python equivalence.py --iters 3 --compare    # 与记录比，任何差异退 1

    # 只比某一个 spot
    python equivalence.py --iters 3 --compare --only retrocam/frontier-i

# 它与 bench --compare 的分工

    equivalence.py --compare   plan 级：**产物**必须逐字节相同（更强）
    bench --compare            KPI 级：**指标**必须相同，且报时间

两个都过才算改了性能没改结果。
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import candidates  # noqa: E402
import ec_layout as ec  # noqa: E402
import grid_experiment  # noqa: E402
import normalise as norm_mod  # noqa: E402
import reproduce as rep  # noqa: E402
import selftest  # noqa: E402

STORE = os.path.join(HERE, ".bench", "equivalence.json")


def _resolve_board():
    env = os.environ.get("EASYCIRQ_LAYOUT_BOARD", "").strip()
    if env:
        d = env
        if os.path.isdir(os.path.join(d, "pcb")):
            d = os.path.join(d, "pcb")
        return os.path.join(d, "dump2.json"), os.path.join(d, "ec-placed.json")
    fx = os.path.join(HERE, "fixtures")
    if os.path.isfile(os.path.join(fx, "dump2.json")):
        return os.path.join(fx, "dump2.json"), os.path.join(fx, "ec-placed.json")
    legacy = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                          "retrocam-02", "pcb")
    return os.path.join(legacy, "dump2.json"), os.path.join(legacy, "offline", "ec-placed.json")


def plan_sha(plan):
    """与 emit_apply 完全一致的归一化哈希 —— 不另造一套口径。"""
    from emit_apply import normalise as normalise_plan
    norm = normalise_plan(plan)
    return hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()


def route_one(dump_path, place_path, candidate, profile, iters):
    """复刻 bench.run_spot 的取数路径，保证门禁测的就是 bench 测的东西。"""
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    if candidate:
        over = candidates.constants_for(candidate)
        if over:
            cfg["constants"] = {**cfg.get("constants", {}), **over}
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(
        float(cfg.get("grid") or 10), constants=cfg.get("constants"))

    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        place = json.load(f)
    if candidate:
        dump, place, _ = candidates.build(candidate, dump, place)
    dump, place, _ = norm_mod.apply(dump, place)

    t0 = time.time()
    board = rep.ec.Board(dump)
    rep.ec.apply_placement(board, place)
    routed, fails = rep._route(board, cfg)
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    secs = time.time() - t0

    return {
        "plan_sha256": plan_sha(plan),
        "tracks": len(plan.get("tracks") or []),
        "vias": len(plan.get("vias") or []),
        "clearance_violations": kpi.get("clearance_violations"),
        "nets_unconnected": kpi.get("nets_unconnected"),
        "cam_skew": (kpi.get("bus_length_spread_mil") or {}).get("CAM_D"),
        "seconds": round(secs, 2),
    }


def spots(iters):
    dump, place = _resolve_board()
    out = []
    if os.path.exists(dump) and os.path.exists(place):
        out.append(("retrocam/frontier-i", dump, place, "frontier-i", "strict-via-thin"))
    out.append(("selftest", None, None, None, "strict-via-thin"))
    return out


def selftest_route(profile, iters):
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(
        float(cfg.get("grid") or 10), constants=cfg.get("constants"))
    dump = selftest.make_dump()
    place = selftest.make_place()
    dump, place, _ = norm_mod.apply(dump, place)
    t0 = time.time()
    board = rep.ec.Board(dump)
    rep.ec.apply_placement(board, place)
    routed, fails = rep._route(board, cfg)
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    return {
        "plan_sha256": plan_sha(plan),
        "tracks": len(plan.get("tracks") or []),
        "vias": len(plan.get("vias") or []),
        "clearance_violations": kpi.get("clearance_violations"),
        "nets_unconnected": kpi.get("nets_unconnected"),
        "cam_skew": (kpi.get("bus_length_spread_mil") or {}).get("CAM_D"),
        "seconds": round(time.time() - t0, 2),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--write", action="store_true", help="记录当前产物指纹")
    ap.add_argument("--compare", action="store_true", help="与记录比对，有差异退 1")
    ap.add_argument("--only", default=None, help="只跑某个 spot")
    a = ap.parse_args()

    if not (a.write or a.compare):
        ap.error("需要 --write 或 --compare（这道门禁不是用来'看看'的）")

    cur = {}
    for label, dump, place, cand, profile in spots(a.iters):
        if a.only and a.only != label:
            continue
        if dump is None:
            row = selftest_route(profile, a.iters)
        else:
            row = route_one(dump, place, cand, profile, a.iters)
        cur[label] = row
        print("  %-24s %5.1fs  tracks=%-4d vias=%-3d sha=%s"
              % (label, row["seconds"], row["tracks"], row["vias"],
                 row["plan_sha256"][:16]))

    os.makedirs(os.path.dirname(STORE), exist_ok=True)

    if a.write:
        payload = {"iters": a.iters, "spots": cur,
                   "note": "plan_sha256 = sha256(json.dumps(normalise(plan), sort_keys=True)) "
                           "— the same identity emit_apply refuses on"}
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print("\n已记录到 %s" % STORE)
        return 0

    if not os.path.exists(STORE):
        print("\n没有记录可比。先跑一次 --write。")
        return 2
    with open(STORE, encoding="utf-8") as f:
        base = json.load(f)

    bad = 0
    print()
    for label, row in cur.items():
        ref = (base.get("spots") or {}).get(label)
        if not ref:
            print("  %-24s 记录里没有，跳过" % label)
            continue
        same = ref["plan_sha256"] == row["plan_sha256"]
        if not same:
            bad += 1
            print("  %-24s **PLAN CHANGED**" % label)
            print("      记录: %s" % ref["plan_sha256"][:32])
            print("      现在: %s" % row["plan_sha256"][:32])
            for k in ("tracks", "vias", "clearance_violations", "cam_skew"):
                if ref.get(k) != row.get(k):
                    print("      %s: %s -> %s" % (k, ref.get(k), row.get(k)))
        else:
            print("  %-24s plan identical (%s…)" % (label, row["plan_sha256"][:16]))

    print()
    if bad:
        print("等价性门禁：%d 个 spot 的产物变了 —— 这不是无害的性能改动" % bad)
        return 1
    print("等价性门禁：全部 spot 产物逐字节相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
