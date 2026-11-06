#!/usr/bin/env python3
"""把排版**铺开**：给外设加最小附着间距，逐级尝试，取能解且不穿器件的最大间距。

为什么需要它：求解器按**最小线长**摆放，器件挤成一团。实测 M3 只占纸宽的 20%，
M5 占 45% —— 电学没问题，但交付出去很难看，而且白用大纸。

产品为此设计了 `minimumAttachmentDistance`（host-outward 引脚轴间距，5..400 raw，
5-raw 网格，**两端引脚必须显式**）。实测有效：

    M5: 0 → 270×115(45%)   80 → 345×110(58%)   120 → 425×110(72%)   160 → 太宽

但**不能对所有外设都加**：去耦电容与 core 之间是**电源/地**网，而归属校验明确
禁止用"电源/地连通"替代专用分支（`peripheral-direct-missing`）。所以只给
**信号网**相连的外设加提示。

用法：
  python scripts/sch_layout_spread.py --input one-M3.json --out composition-M3.json
  python scripts/sch_layout_spread.py --input ... --out ... --distances 120,80,40
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

RAIL_PREFIXES = ("+", "-")
RAIL_NAMES = {"GND", "AGND", "DGND", "GNDA", "PGND", "EARTH",
              "VBAT_RAW", "VBAT", "VSYS", "VIN", "VCC", "VDD", "VSS",
              "12V", "5V", "3V3", "3V8"}


def default_exe() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    p = pathlib.Path(base) / "EasyCirq" / "bin" / "easycirq.exe"
    return str(p)


def is_rail(name: str) -> bool:
    """电源/地网：不能用来做归属附着（规则明确禁止）。"""
    n = (name or "").strip().upper()
    if not n:
        return True
    if n in RAIL_NAMES:
        return True
    if n.startswith(RAIL_PREFIXES):
        return True
    return "GND" in n


def build_hints(src, distance, verbose=False):
    """只为**信号网**相连的外设加 attachTo + minimumAttachmentDistance。"""
    conn = src["connectivity"]
    mod = conn["modules"][0]
    core = mod["coreComponents"][0]
    netname = {n["id"]: (n.get("name") or "") for n in conn["nets"]}
    pins_of = {}
    for x in conn["connections"]:
        pins_of.setdefault(x["componentId"], []).append(x)
    core_pins = pins_of.get(core) or []

    hints, skipped = [], []
    for pid in (mod.get("peripheralComponents") or []):
        hit = None
        for m in (pins_of.get(pid) or []):
            if is_rail(netname.get(m["netId"], "")):
                continue                      # 电源/地：不能当附着关系
            for c in core_pins:
                if m["netId"] == c["netId"]:
                    hit = (m, c, netname.get(m["netId"], ""))
                    break
            if hit:
                break
        if hit:
            hints.append({"componentId": pid, "pinNumber": hit[0]["pinNumber"],
                          "attachTo": {"componentId": core,
                                       "pinNumber": hit[1]["pinNumber"]},
                          "minimumAttachmentDistance": distance})
        else:
            hints.append({"componentId": pid})
            skipped.append(pid)
    if verbose:
        print("      带附着提示 %d / %d（电源/地相连或无信号直连的 %d 个不加）"
              % (len(hints) - len(skipped), len(hints), len(skipped)))
    return hints


def run_layout(exe, probe, out):
    out.unlink(missing_ok=True)
    p = subprocess.run([exe, "sch", "lib-layout", "--from", str(probe),
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600)
    ok = out.is_file()
    msg = ((p.stdout or "") + (p.stderr or "")).strip()
    return ok, msg


def measure(doc):
    """返回 (宽, 高, 穿器件数)。穿器件判定与 Go 的 SegmentEntersBody 对齐。"""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import sch_layout_review as R
    parts, wires, _, _ = R.extract(doc)
    if not parts:
        return 0.0, 0.0, 0
    b = R.union(list(parts.values()))
    q = R.quality(parts, wires, doc.get("sheet") or
                  {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1})
    return b[2] - b[0], b[3] - b[1], len(q["crossings"])


def spread(input_path, out_path, exe, distances, verbose=True):
    src = json.loads(pathlib.Path(input_path).read_text(encoding="utf-8"))
    sheet = src.get("sheet") or {"minX": 0, "minY": 0}
    page_w = sheet["maxX"] - sheet["minX"]
    page_h = sheet["maxY"] - sheet["minY"]
    # 可用区：留出边距（与 compose 的 10 raw 页边一致，再宽一点更保险）
    usable_w = max(1.0, page_w - 40)
    usable_h = max(1.0, page_h - 40)

    trials = []
    best = None
    for d in distances:
        trial = json.loads(json.dumps(src))
        trial["layoutModules"][0]["peripherals"] = (
            build_hints(src, d) if d else
            [{"componentId": c} for c in
             (src["connectivity"]["modules"][0].get("peripheralComponents") or [])])
        probe = pathlib.Path(str(out_path)).with_suffix(".probe.json")
        probe.write_text(json.dumps(trial, ensure_ascii=False), encoding="utf-8")
        cand = pathlib.Path(str(out_path)).with_suffix(".cand.json")
        ok, msg = run_layout(exe, probe, cand)
        if not ok:
            trials.append((d, None, msg.split(":")[-1][:46]))
            continue
        doc = json.loads(cand.read_text(encoding="utf-8"))
        w, h, cross = measure(doc)
        trials.append((d, (w, h, cross), ""))
        # **两向都填满**：取 min(宽比, 高比) 最大者。
        # 只按最宽选会得到"细长条"，纵向仍然空着，看起来更怪。
        fill = min(w / usable_w, h / usable_h)
        if cross == 0 and (best is None or fill > best[3]):
            best = (w, h, d, fill, doc)
        probe.unlink(missing_ok=True)

    if best is None:
        # 全部失败：用原始（不带提示）再跑一次
        raise SystemExit("spread: 所有间距都失败，请检查输入")

    for d, m, why in trials:
        if m:
            print("      间距 %3d → %5.0f×%-5.0f 占宽 %3.0f%% 占高 %3.0f%%  穿器件 %d"
                  % (d, m[0], m[1], m[0] / page_w * 100,
                     m[1] / page_h * 100, m[2]))
        else:
            print("      间距 %3d → 失败 %s" % (d, why))
    w, h, d, fill, doc = best
    if verbose:
        print("      采用间距 %d：%.0f×%.0f（占宽 %.0f%% 占高 %.0f%% 两向填充 %.0f%%）"
              % (d, w, h, w / page_w * 100, h / page_h * 100, fill * 100))
    pathlib.Path(out_path).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"distance": d, "width": w, "height": h, "trials": trials}


def main() -> int:
    ap = argparse.ArgumentParser(description="把排版铺开：逐级尝试最小附着间距")
    ap.add_argument("--input", action="append", required=True,
                    help="one-模块.json（可多个，按 --out-dir 命名输出）")
    ap.add_argument("--out", help="单个输入时的输出路径")
    ap.add_argument("--out-dir", help="多个输入时的输出目录")
    ap.add_argument("--distances", default="120,80,40",
                    help="逗号分隔，从大到小尝试（含 0 表示不铺开）")
    ap.add_argument("--exe", default=default_exe())
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    distances = [float(x) for x in args.distances.split(",") if x.strip()] + [0.0]
    results = []
    for inp in args.input:
        stem = pathlib.Path(inp).stem
        mid = stem[len("one-"):] if stem.startswith("one-") else stem
        if args.out and len(args.input) == 1:
            out = args.out
        else:
            base = pathlib.Path(args.out_dir or "reports")
            base.mkdir(parents=True, exist_ok=True)
            out = str(base / ("composition-%s.json" % mid))
        print("  %s" % mid)
        r = spread(inp, out, args.exe, distances)
        r["module"] = mid
        r["out"] = out
        results.append(r)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
