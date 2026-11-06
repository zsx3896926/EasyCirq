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


# 标准纸（raw，0.01 inch），按面积从小到大
PAPERS = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}


def pick_paper(doc, margin=20.0):
    """按内容外框挑能装下的最小标准纸；装不下就用 A0。"""
    xs0, ys0, xs1, ys1 = [], [], [], []
    for m in doc.get("measurements") or []:
        b = m.get("bbox")
        if not b:
            continue
        xs0.append(b["minX"]); xs1.append(b["maxX"])
        ys0.append(b["minY"]); ys1.append(b["maxY"])
    if not xs0:
        return None, None
    w = (max(xs1) - min(xs0)) + 2 * margin
    h = (max(ys1) - min(ys0)) + 2 * margin
    for name in ("A4", "A3", "A2", "A1", "A0"):
        pw, ph = PAPERS[name]
        # 横竖都试
        if (w <= pw and h <= ph) or (h <= pw and w <= ph):
            return name, (pw, ph) if (w <= pw and h <= ph) else (ph, pw)
    return "A0", PAPERS["A0"]


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
    ap.add_argument("--auto-paper", action="store_true",
                    help="按内容试排最小标准纸。默认**关**：实测 A3 会让"
                         "'模块框不切器件/导线'退步（框溢出页面）")
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for inp in args.input:
        stem = pathlib.Path(inp).stem
        mid = stem[4:] if stem.startswith("one-") else stem
        doc = json.loads(pathlib.Path(inp).read_text(encoding="utf-8"))
        target = out / ("composition-%s.json" % mid)
        if args.auto_paper:
            # 从小到大**实际试排**：装得下不等于排得出（模块框/位号/网标
            # 都要额外空间，实测 A4 按尺寸够却解不出来）。
            order = ["A4", "A3", "A2", "A1", "A0"]
            picked = None
            for pname in order:
                pw, ph = PAPERS[pname]
                probe_doc = json.loads(json.dumps(doc))
                probe_doc["sheet"] = {"minX": 0.0, "minY": 0.0,
                                      "maxX": pw, "maxY": ph}
                ok_probe, _dt, _msg = try_solve(args.exe, probe_doc, True,
                                                out / ("probe-%s.json" % mid),
                                                args.budget)
                if ok_probe:
                    picked = (pname, (pw, ph))
                    break
            if picked:
                doc["sheet"] = {"minX": 0.0, "minY": 0.0,
                                "maxX": float(picked[1][0]),
                                "maxY": float(picked[1][1])}
                print("  %-3s 自动选纸 %s（%g×%g）"
                      % (mid, picked[0], picked[1][0], picked[1][1]))

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
