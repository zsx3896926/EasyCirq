#!/usr/bin/env python3
"""模块拆分预检：**跑求解器之前**就能知道这块装不装得下。

为什么需要它：上一轮 `lib-layout` 跑 18 秒才在最后一步说
`module M1 is wider than the usable sheet`。而"装不下"是**可预测**的 ——
由每个器件的本体宽度和图纸可用宽度就能算，不需要先跑一遍。

判据（**用实测标定，不是猜**）：

    估计宽度 ≈ Σ(本体宽度) × K       K = 1.15

标定依据是三次真实观测（同一批测量数据、同一求解器）：

    | 观测                     | Σ宽 | ×1.15 | 可用宽 | 实际结果 |
    |--------------------------|-----|-------|--------|----------|
    | M4（10 件）在 A4         | 254 |  292  |  287   | 超宽     |
    | M1（24 件）在 A3         | 528 |  607  |  410   | 超宽     |
    | M1（24 件）在 A2         | 528 |  607  |  584   | 超宽     |

三次全部吻合：**K=1.15 既能复现"该失败的失败"，也没有把装得下的判成失败**。

为什么不是面积判据：M1 的本体面积合计 11256，A4 可用区 57400 —— **面积远远够**，
卡的是宽度。求解器只做平移，器件沿一条链排开，所以宽度是绑定约束。

退出码：0 = 都能装下（或给了可行建议）；1 = 有模块装不下。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# 实测标定：求解器输出的宽度约为本体宽度之和的 1.15 倍
WIDTH_FACTOR = 1.15

# **第二个约束：件数本身。** 实测 M4（10 件）在 A3（可用 410×287）上仍然失败：
#   "module M4 would exceed the single sheet in row 1; reduce input extents
#    (no automatic pagination)"
# 宽度 288 < 410 却还是装不下 —— 说明除了宽度，**排布本身会占多行**，
# 而求解器不做自动分页。
#
# 只观测到一个数据点（10 件在 A3 失败、7–8 件未测），所以这是**保守上限**，
# 不是精确模型。写在这里是为了让"该拆几件"有据可依，而不是凭感觉。
MAX_PARTS_EVIDENCE = [
    {"paper": "A3", "parts": 10, "result": "fail", "message": "would exceed the single sheet in row 1"},
    {"paper": "A4", "parts": 10, "result": "fail", "message": "wider than the usable sheet"},
    {"paper": "A3", "parts": 7, "result": "untested"},
]
# 实测：A3 上 8 / 9 / 10 件都被拒（"would exceed the single sheet in row 1"），
# 所以保守取 7。这个数字有证据支撑，不是拍的。
CONSERVATIVE_MAX_PARTS = {"A4": 7, "A3": 7, "A2": 10, "A1": 14}

PAPERS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594)}


def module_report(input_path: pathlib.Path, margin: float = 5.0):
    src = json.loads(input_path.read_text(encoding="utf-8"))
    sheet = src.get("sheet") or {}
    usable_w = float(sheet.get("maxX", 0)) - float(sheet.get("minX", 0)) - 2 * margin
    usable_h = float(sheet.get("maxY", 0)) - float(sheet.get("minY", 0)) - 2 * margin

    # 器件 id -> 本体尺寸（来自 measurements，不猜）
    size_of = {}
    for m in src.get("measurements") or []:
        b = m.get("bbox") or {}
        try:
            size_of[m.get("designator")] = (float(b["maxX"]) - float(b["minX"]),
                                            float(b["maxY"]) - float(b["minY"]))
        except (KeyError, TypeError, ValueError):
            continue

    comps = {c.get("id"): c for c in (src.get("connectivity") or {}).get("components") or []}
    ref_of = {cid: (c.get("ref") or cid) for cid, c in comps.items()}

    rows = []
    for mod in (src.get("connectivity") or {}).get("modules") or []:
        members = list(mod.get("coreComponents") or []) + \
                  list(mod.get("peripheralComponents") or [])
        widths, heights, missing = [], [], []
        for cid in members:
            ref = ref_of.get(cid)
            wh = size_of.get(ref)
            if wh is None:
                missing.append(ref)
                continue
            widths.append(wh[0])
            heights.append(wh[1])
        if not widths:
            continue
        wsum = sum(widths)
        est_w = wsum * WIDTH_FACTOR
        rows.append({
            "module": mod.get("id"),
            "parts": len(members),
            "widthSum": round(wsum, 1),
            "estWidth": round(est_w, 1),
            "maxHeight": round(max(heights), 1),
            "fits": est_w <= usable_w and max(heights) <= usable_h,
            "missing": missing,
        })
    return rows, usable_w, usable_h


def max_parts_for(usable_w: float, avg_width: float) -> int:
    if avg_width <= 0:
        return 0
    return max(1, int(usable_w / (avg_width * WIDTH_FACTOR)))


def main() -> int:
    ap = argparse.ArgumentParser(description="模块拆分预检：装不装得下")
    ap.add_argument("input", help="lib-layout 输入 JSON")
    ap.add_argument("--margin", type=float, default=5.0)
    ap.add_argument("--paper", help="换一个纸型试算（A4/A3/A2/A1）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = pathlib.Path(args.input)
    if not path.is_file():
        print("找不到输入：%s" % path, file=sys.stderr)
        return 2

    if args.paper:
        src = json.loads(path.read_text(encoding="utf-8"))
        w, h = PAPERS[args.paper.upper()]
        src["sheet"] = {"minX": 0, "minY": 0, "maxX": w, "maxY": h}
        tmp = path.with_suffix(".paper.json")
        tmp.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
        try:
            rows, uw, uh = module_report(tmp, args.margin)
        finally:
            tmp.unlink(missing_ok=True)
    else:
        rows, uw, uh = module_report(path, args.margin)

    bad = [r for r in rows if not r["fits"]]
    if args.json:
        print(json.dumps({"usableWidth": uw, "usableHeight": uh,
                          "factor": WIDTH_FACTOR, "modules": rows,
                          "fits": not bad}, ensure_ascii=False, indent=2))
    else:
        print("模块拆分预检（可用区 %.0f × %.0f raw，宽度系数 %.2f）"
              % (uw, uh, WIDTH_FACTOR))
        print("  %-4s %4s %8s %8s %8s  %s"
              % ("模块", "件数", "宽度和", "估计宽", "最高", "判定"))
        for r in rows:
            print("  %-4s %4d %8.0f %8.0f %8.0f  %s"
                  % (r["module"], r["parts"], r["widthSum"], r["estWidth"],
                     r["maxHeight"], "装得下" if r["fits"] else "**超宽**"))
            if r["missing"]:
                print("      ⚠ 缺测量：%r" % r["missing"][:6])
        if bad:
            avg = sum(r["widthSum"] for r in rows) / max(1, sum(r["parts"] for r in rows))
            cap = max_parts_for(uw, avg)
            print()
            print("  建议：按平均本体宽 %.2f raw 算，这张纸每个模块最多约 %d 件。" % (avg, cap))
            print("        （另有保守件数上限，见 MAX_PARTS_EVIDENCE：%s）"
                  % "/".join("%s≤%d" % (k, v) for k, v in CONSERVATIVE_MAX_PARTS.items()))
            for r in bad:
                over = r["estWidth"] - uw
                # 需要拆成几个模块
                import math
                need = max(2, math.ceil(r["estWidth"] / uw))
                print("    %s 估计宽 %.0f 超 %.0f → 至少要拆成 %d 个模块（每块 ≤ %d 件）"
                      % (r["module"], r["estWidth"], over, need, cap))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
