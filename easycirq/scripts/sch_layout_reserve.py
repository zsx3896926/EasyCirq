#!/usr/bin/env python3
"""排版的**位号预留区**：带它求解，解不出就自动回退（并如实报告）。

为什么需要这一层：
  · `validateLibRoutingEdge` / `libValidateWireTextClearance` 都会检查
    "导线不许穿过位号预留区"（`TextBBoxes`）
  · 但预留区**只对能解出来的模块有效**：实测 M3/M4/M5 1 秒内解出且 0 穿越，
    M1（24 件）/M2 在 100 万候选上限内解不出

所以策略是**逐模块尝试 + 自动回退**：
  1. 先带预留区求解（能解 → 导线上不会穿位号）
  2. 解不出 → 退回不带预留区（保持原有可解性），并在结果里**标明**

**键名必须是 `textBboxes`**（小写 b）。Go 的严格解码器大小写敏感，
写成 `textBBoxes` 会被静默判为未知字段 —— 这个坑消耗了 7 轮（#78）。

用法：
  python scripts/sch_layout_reserve.py --input one-M3.json --out composition-M3.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FS = 7.0
WIDTH_K = 0.75
DX = -2.0          # 实测：文字框左边 = minX - 2.0
DY0 = -0.5         # 实测：文字框下边 = maxY - 0.5
DY1 = 7.5          # 实测：文字框上边 = maxY + 7.5


def label_box(bbox, designator):
    tw = max(6.0, WIDTH_K * FS * max(1, len(str(designator or ""))))
    return {"minX": round(bbox["minX"] + DX, 1),
            "minY": round(bbox["maxY"] + DY0, 1),
            "maxX": round(bbox["minX"] + DX + tw, 1),
            "maxY": round(bbox["maxY"] + DY1, 1)}


def default_exe() -> str:
    base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home())
    return str(pathlib.Path(base) / "EasyCirq" / "bin" / "easycirq.exe")


def try_solve(exe, doc, reserve, out_path, budget=None):
    d = json.loads(json.dumps(doc))
    if budget is not None:
        d["maxCandidates"] = budget
    for meas in d.get("measurements") or []:
        b = meas.get("bbox")
        if not b:
            continue
        if reserve:
            meas["textBboxes"] = [label_box(b, meas.get("designator"))]
        else:
            meas.pop("textBboxes", None)
    probe = pathlib.Path(str(out_path)).with_suffix(".probe.json")
    probe.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    pathlib.Path(out_path).unlink(missing_ok=True)
    t0 = time.time()
    p = subprocess.run([exe, "sch", "lib-layout", "--from", str(probe),
                        "--out", str(out_path)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600)
    dt = time.time() - t0
    ok = pathlib.Path(out_path).is_file()
    probe.unlink(missing_ok=True)
    return ok, dt, ((p.stdout or p.stderr) or "").strip()[:110]


def main() -> int:
    ap = argparse.ArgumentParser(description="带位号预留区求解，解不出自动回退")
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--exe", default=default_exe())
    ap.add_argument("--budget", type=int, default=1000000)
    ap.add_argument("--no-reserve", action="store_true",
                    help="完全不使用预留区（回到旧行为）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for inp in args.input:
        stem = pathlib.Path(inp).stem
        mid = stem[4:] if stem.startswith("one-") else stem
        doc = json.loads(pathlib.Path(inp).read_text(encoding="utf-8"))
        target = out / ("composition-%s.json" % mid)

        if args.no_reserve:
            ok, dt, msg = try_solve(args.exe, doc, False, target)
            note = "预留区未启用（--no-reserve）"
        else:
            ok, dt, msg = try_solve(args.exe, doc, True, target, args.budget)
            if ok:
                note = "带预留区 ✅（导线不会穿位号）"
            else:
                ok, dt2, msg2 = try_solve(args.exe, doc, False, target, args.budget)
                dt += dt2
                note = ("带预留区解不出（%.0f 秒）→ **已回退**到无预留区；"
                        "该模块的导线仍可能穿位号" % (dt - dt2)) if ok \
                    else "两种都解不出"
        results.append({"module": mid, "ok": ok, "seconds": round(dt, 1),
                        "note": note, "error": "" if ok else msg})
        print("  %-3s %s  %5.1f 秒  %s"
              % (mid, "✅" if ok else "❌", dt, note), flush=True)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
