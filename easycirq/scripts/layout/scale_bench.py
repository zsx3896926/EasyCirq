#!/usr/bin/env python3
"""规模基准：测出这套工具链在什么规模上失效，**而不是猜**。

# 为什么每个点在独立进程里跑

A* 的缓冲是 C 里的 malloc，Python 的 tracemalloc 看不到；而且大图会直接
MemoryError 把进程带走。所以父进程只造板 + 收数，**每个规模点在子进程里跑**，
子进程自己报峰值内存与耗时，崩了就是一个明确的失败行，不会带走整张表。

# 两条轴分开测（它们不是一回事）

    --mode area   **板面积**：同一块设计摊到更大的板上 ⇒ 节点数涨，网络数不变
                  → 这条轴测的是 **内存墙**（缓冲按 L*W*H 稠密分配）

    --mode nets   **网络数**：把这块设计平铺 k 份 ⇒ 网络数涨 k 倍
                  → 这条轴测的是 **时间**（A* 调用次数随腿数涨）

# 用法

    python scale_bench.py --mode area --factors 1,2,4,8 --iters 1
    python scale_bench.py --mode nets --factors 1,2,4 --iters 1
    python scale_bench.py --all --iters 1

未跑或没跑成的点**照实写 FAIL/NOT RUN**，不外推。
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FIX = HERE / "fixtures"


# ── 子进程：只跑一个点，报自己的峰值内存与耗时 ──────────────────────────
def run_one(dump_path, place_path, iters, profile):
    import platform

    def peak_mb():
        if platform.system() != "Windows":
            try:
                import resource
                return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
            except Exception:                       # noqa: BLE001
                return -1.0
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        # argtypes/restype 必须显式声明：ctypes 默认把返回值当 int，
        # 不声明时调用会静默失败并返回 0（第一版就是这样量出 0.0 MB）。
        fn = ctypes.windll.psapi.GetProcessMemoryInfo
        fn.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        fn.restype = wt.BOOL
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        if not fn(ctypes.windll.kernel32.GetCurrentProcess(),
                  ctypes.byref(c), c.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return c.PeakWorkingSetSize / (1024.0 * 1024.0)

    import candidates  # noqa: E402
    import grid_experiment  # noqa: E402
    import normalise as norm_mod  # noqa: E402
    import reproduce as rep  # noqa: E402

    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    rep.use_grid(cfg.get("grid"))
    ec = grid_experiment.load_module(float(cfg.get("grid") or 10),
                                     constants=cfg.get("constants"))
    rep.ec = ec

    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    with open(place_path, encoding="utf-8") as f:
        place = json.load(f)
    dump, place, _ = norm_mod.apply(dump, place)

    board = ec.Board(dump)
    ec.apply_placement(board, place)

    base = peak_mb()
    t0 = time.perf_counter()
    try:
        routed, fails = rep._route(board, cfg)
        plan = ec.plan_from(board, routed)
        kpi = ec.report(board, routed, fails, [], plan)
        secs = time.perf_counter() - t0
        out = {
            "ok": True,
            "W": board.w, "H": board.h, "L": cfg.get("layers", 2),
            "nodes": board.w * board.h * cfg.get("layers", 2),
            "comps": len(board.comps) if hasattr(board, "comps") else None,
            "nets": len(board.nets),
            "tracks": len(plan.get("tracks") or []),
            "unrouted": kpi.get("unrouted_legs"),
            "clearance": kpi.get("clearance_violations"),
            "secs": round(secs, 2),
            # 峰值是"历史最高"，减 base 没有意义；只报绝对值，
            # 另附运行前的基线供参考。
            "peak_mb": round(peak_mb(), 1),
            "peak_base_mb": round(base, 1),
        }
    except MemoryError:
        out = {"ok": False, "why": "MemoryError",
               "W": board.w, "H": board.h,
               "nodes": board.w * board.h * cfg.get("layers", 2),
               "nets": len(board.nets),
               "secs": round(time.perf_counter() - t0, 2),
               "peak_total_mb": round(peak_mb(), 1)}
    print("RESULT " + json.dumps(out))
    return 0


# ── 造板：面积放大 ──────────────────────────────────────────────────────
def make_area(dump, place, k):
    """把整块设计摊到 k 倍的坐标上：节点数涨，网络数不变。"""
    d = json.loads(json.dumps(dump))
    r = d.get("result") or d
    for c in r.get("components") or []:
        if isinstance(c.get("x"), (int, float)):
            c["x"] *= k
        if isinstance(c.get("y"), (int, float)):
            c["y"] *= k
        for p in c.get("pads") or []:
            if isinstance(p.get("x"), (int, float)):
                p["x"] *= k
            if isinstance(p.get("y"), (int, float)):
                p["y"] *= k
        bb = c.get("bbox") or {}
        for key in ("minX", "maxX"):
            if isinstance(bb.get(key), (int, float)):
                bb[key] *= k
        for key in ("minY", "maxY"):
            if isinstance(bb.get(key), (int, float)):
                bb[key] *= k
    ol = r.get("outline") or {}
    bb = ol.get("bbox") or {}
    for key in ("minX", "maxX"):
        if isinstance(bb.get(key), (int, float)):
            bb[key] *= k
    for key in ("minY", "maxY"):
        if isinstance(bb.get(key), (int, float)):
            bb[key] *= k
    if ol.get("points"):
        ol["points"] = [[px * k, py * k] for px, py in ol["points"]]

    p = json.loads(json.dumps(place))
    for v in p.values():
        if isinstance(v, dict):
            if isinstance(v.get("x"), (int, float)):
                v["x"] *= k
            if isinstance(v.get("y"), (int, float)):
                v["y"] *= k
    return d, p


# ── 造板：网络数放大 ────────────────────────────────────────────────────
def make_tiled(dump, place, k):
    """把设计平铺 k 份：每份的位号和网络名加后缀，坐标按网格错开。"""
    if k <= 1:
        return json.loads(json.dumps(dump)), json.loads(json.dumps(place))

    d = json.loads(json.dumps(dump))
    r = d.get("result") or d
    comps = r.get("components") or []
    ol = r.get("outline") or {}
    bb = (ol.get("bbox") or {})
    span_x = (bb.get("maxX") or 0) - (bb.get("minX") or 0)
    span_y = (bb.get("maxY") or 0) - (bb.get("minY") or 0)
    if span_x <= 0 or span_y <= 0:
        raise SystemExit("outline bbox 不可用，无法平铺")

    # 尽量排成接近正方形
    cols = 1
    while cols * cols < k:
        cols += 1
    rows = (k + cols - 1) // cols
    gap = 200.0

    new_comps = []
    for i in range(k):
        ox = (i % cols) * (span_x + gap)
        oy = (i // cols) * (span_y + gap)
        sfx = "" if i == 0 else "_c%d" % i
        for c in comps:
            cc = json.loads(json.dumps(c))
            cc["designator"] = str(c.get("designator")) + sfx
            cc["primitiveId"] = str(c.get("primitiveId")) + ("x%d" % i if i else "")
            cc["x"] = (c.get("x") or 0) + ox
            cc["y"] = (c.get("y") or 0) + oy
            b = cc.get("bbox") or {}
            for key in ("minX", "maxX"):
                if isinstance(b.get(key), (int, float)):
                    b[key] += ox
            for key in ("minY", "maxY"):
                if isinstance(b.get(key), (int, float)):
                    b[key] += oy
            for p in cc.get("pads") or []:
                p["x"] = (p.get("x") or 0) + ox
                p["y"] = (p.get("y") or 0) + oy
                if p.get("net") and i:
                    p["net"] = str(p["net"]) + sfx
                p["primitiveId"] = str(p.get("primitiveId")) + (
                    "x%d" % i if i else "")
            new_comps.append(cc)
    r["components"] = new_comps

    nb = ol.setdefault("bbox", {})
    nb["minX"] = bb.get("minX", 0)
    nb["minY"] = bb.get("minY", 0)
    nb["maxX"] = bb.get("minX", 0) + cols * span_x + (cols - 1) * gap
    nb["maxY"] = bb.get("minY", 0) + rows * span_y + (rows - 1) * gap
    ol.pop("points", None)     # 平铺后轮廓点不再成立，交给 bbox

    p = json.loads(json.dumps(place))
    newp = {}
    for i in range(k):
        ox = (i % cols) * (span_x + gap)
        oy = (i // cols) * (span_y + gap)
        sfx = "" if i == 0 else "_c%d" % i
        for name, v in p.items():
            if not isinstance(v, dict):
                continue
            vv = dict(v)
            vv["x"] = (v.get("x") or 0) + ox
            vv["y"] = (v.get("y") or 0) + oy
            newp[str(name) + sfx] = vv
    return d, newp


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["area", "nets"], default="area")
    ap.add_argument("--all", action="store_true", help="两条轴都跑")
    ap.add_argument("--factors", default="1,2,4,8")
    ap.add_argument("--iters", type=int, default=1)
    ap.add_argument("--profile", default="strict-via-thin")
    ap.add_argument("--timeout", type=int, default=1800, help="单点超时秒数")
    ap.add_argument("--run-one", nargs=3, metavar=("DUMP", "PLACE", "ITERS"),
                    help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.run_one:
        return run_one(a.run_one[0], a.run_one[1], int(a.run_one[2]), a.profile)

    dump = json.loads((FIX / "dump2.json").read_text(encoding="utf-8"))
    place = json.loads((FIX / "ec-placed.json").read_text(encoding="utf-8"))
    factors = [int(x) for x in a.factors.split(",") if x.strip()]

    modes = ["area", "nets"] if a.all else [a.mode]
    rows = []

    with tempfile.TemporaryDirectory(prefix="scalebench-") as td:
        td = pathlib.Path(td)
        for mode in modes:
            for k in factors:
                label = f"{mode} x{k}"
                try:
                    dd, pp = (make_area(dump, place, k) if mode == "area"
                              else make_tiled(dump, place, k))
                except SystemExit as exc:
                    rows.append({"label": label, "status": "BUILD-FAIL",
                                 "why": str(exc)})
                    print(f"[{label}] 造板失败: {exc}", flush=True)
                    continue

                dp = td / f"{mode}-{k}-dump.json"
                lp = td / f"{mode}-{k}-place.json"
                dp.write_text(json.dumps(dd), encoding="utf-8")
                lp.write_text(json.dumps(pp), encoding="utf-8")

                print(f"[{label}] 运行中 ...", flush=True)
                t0 = time.perf_counter()
                try:
                    p = subprocess.run(
                        [sys.executable, str(pathlib.Path(__file__).resolve()),
                         "--run-one", str(dp), str(lp), str(a.iters),
                         "--profile", a.profile],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=a.timeout)
                except subprocess.TimeoutExpired:
                    rows.append({"label": label, "status": "TIMEOUT",
                                 "why": f">{a.timeout}s"})
                    print(f"[{label}] 超时", flush=True)
                    continue

                wall = time.perf_counter() - t0
                payload = None
                for line in (p.stdout or "").splitlines():
                    if line.startswith("RESULT "):
                        payload = json.loads(line[len("RESULT "):])
                if payload is None:
                    tail = ((p.stderr or "") + (p.stdout or "")).strip().splitlines()
                    rows.append({"label": label, "status": "CRASH",
                                 "why": (tail[-1][:160] if tail else "no output"),
                                 "rc": p.returncode, "wall": round(wall, 1)})
                    print(f"[{label}] 崩溃 rc={p.returncode}", flush=True)
                    continue

                payload["label"] = label
                payload["status"] = "OK" if payload.get("ok") else "FAIL"
                payload["wall"] = round(wall, 1)
                rows.append(payload)
                if payload.get("ok"):
                    print(f"[{label}] W×H×L={payload['W']}x{payload['H']}x"
                          f"{payload['L']} nodes={payload['nodes']:,} "
                          f"nets={payload['nets']} {payload['secs']}s "
                          f"peak={payload['peak_mb']}MB", flush=True)
                else:
                    print(f"[{label}] {payload.get('status')} "
                          f"{payload.get('why')} peak={payload.get('peak_total_mb')}MB",
                          flush=True)

    print()
    print("| 档位 | 状态 | W×H×L | 节点 | 网络 | 走线 | 未通 | 间距违规 "
          "| 耗时 | 峰值内存 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r.get("label"), r.get("status"),
            ("%sx%sx%s" % (r.get("W"), r.get("H"), r.get("L")))
            if r.get("W") else "-",
            ("%d" % r["nodes"]) if r.get("nodes") else "-",
            r.get("nets", "-"), r.get("tracks", "-"),
            r.get("unrouted", "-"), r.get("clearance", "-"),
            ("%ss" % r["secs"]) if r.get("secs") else "-",
            ("%s MB" % r["peak_mb"]) if r.get("peak_mb") else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
