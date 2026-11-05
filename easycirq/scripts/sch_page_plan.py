#!/usr/bin/env python3
"""页面规划：**按实测包络决定分几页、每页用多大的纸**。

为什么需要它：`lib-layout` 只做平移、且不做自动分页（报错原话：
*no automatic pagination*）。装不下时，**加纸**通常比**拆模块**更好 ——
拆会破坏电气完整性（孤立件、跨模块网、外设与 core 失去共享网），加纸不会。

实测教训（friction #50）：
  • 一模块一页 + A1，**5/5 模块一次通过**，含 24 件的整块
  • 但估计公式对小模块会**低估**（M3 估 196 → 判 A4，实测 A4 仍超宽）

所以本工具分成两件事，别混为一谈：

  1. `--plan`：按估计包络给出**候选**页划分与纸型 —— 用来排除明显不可能的
  2. `--confirm`：用一次真实 `lib-layout` 运行**确认**某页真的装得下

**公式不能用来断言"一定装得下"，只能用来排除"一定装不下"。**

用法：
  python scripts/sch_page_plan.py --input reports/x/layout-input-P1.json \\
      --input reports/x/layout-input-P2.json --out reports/x/page-plan.json
  python scripts/sch_page_plan.py --input ... --confirm --exe <easycirq>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-page-plan/v1"
WIDTH_FACTOR = 1.15          # 实测标定：见 sch_module_fit.py 的说明
HEIGHT_SLACK = 1.5           # 行距与走线的粗略余量
MARGIN = 5.0
PAPERS = [("A4", 297, 210), ("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594)]
ORDER = {name: i for i, (name, _, _) in enumerate(PAPERS)}


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def module_envelopes(src):
    """按 measurements 的本体尺寸算每个模块的估计包络。"""
    size_of = {}
    for m in src.get("measurements") or []:
        b = m.get("bbox") or {}
        try:
            size_of[m.get("designator")] = (float(b["maxX"]) - float(b["minX"]),
                                            float(b["maxY"]) - float(b["minY"]))
        except (KeyError, TypeError, ValueError):
            continue
    ref_of = {c.get("id"): c.get("ref")
              for c in (src.get("connectivity") or {}).get("components") or []}
    out = []
    for mod in (src.get("connectivity") or {}).get("modules") or []:
        members = (mod.get("coreComponents") or []) + \
                  (mod.get("peripheralComponents") or [])
        ws, hs, missing = [], [], []
        for cid in members:
            wh = size_of.get(ref_of.get(cid))
            if wh is None:
                missing.append(ref_of.get(cid))
                continue
            ws.append(wh[0])
            hs.append(wh[1])
        if not ws:
            continue
        out.append({
            "module": mod.get("id"),
            "title": mod.get("title") or mod.get("name") or "",
            "parts": len(members),
            "estWidth": round(sum(ws) * WIDTH_FACTOR, 1),
            "estHeight": round(max(hs) * HEIGHT_SLACK, 1),
            "missingMeasurements": missing,
        })
    return out


def smallest_paper(w, h, floor="A4"):
    start = ORDER.get(floor, 0)
    for name, pw, ph in PAPERS[start:]:
        if w <= pw - 2 * MARGIN and h <= ph - 2 * MARGIN:
            return name
    return None


def build_plan(rows, floor="A4", page_prefix="P"):
    pages = []
    for i, r in enumerate(rows):
        # **图纸名按模块命名**（用户要求）：`P1_车辆输入与主5V` 这种。
        # 让图纸本身说清"这一页是干什么的"，而不是靠编号去对照。
        title = (r.get("title") or r["module"] or "").strip()
        safe = "".join(ch for ch in title if ch not in "\\/:*?\"<>|").strip()
        page_name = "%s%d_%s" % (page_prefix, i + 1, safe) if safe else \
            "%s%d_%s" % (page_prefix, i + 1, r["module"])
        pages.append({
            "page": "%s%d" % (page_prefix, i + 1),
            "pageName": page_name,
            "module": r["module"],
            "moduleTitle": title,
            "parts": r["parts"],
            "estWidth": r["estWidth"],
            "estHeight": r["estHeight"],
            "suggestedPaper": smallest_paper(r["estWidth"], r["estHeight"], floor),
            "confirmedPaper": None,
        })
    return pages


def confirm_page(src_path, module, paper, exe, tmp_dir):
    """用一次真实 lib-layout 运行确认这一页装得下。"""
    src = load(src_path)
    conn = src["connectivity"]
    mod = next((m for m in conn["modules"] if m["id"] == module), None)
    if mod is None:
        return False, "模块 %r 不在该输入里" % module
    members = set((mod.get("coreComponents") or []) +
                  (mod.get("peripheralComponents") or []))
    conn["components"] = [c for c in conn["components"] if c["id"] in members]
    conn["connections"] = [x for x in conn["connections"] if x["componentId"] in members]
    kept = {x["netId"] for x in conn["connections"]}
    conn["nets"] = [n for n in conn["nets"] if n["id"] in kept]
    conn["modules"] = [mod]
    refs = {c["ref"] for c in conn["components"]}
    src["measurements"] = [m for m in src.get("measurements") or []
                           if m.get("designator") in refs]
    it = next((x for x in src.get("layoutModules") or [] if x.get("id") == module), None)
    if it:
        it["netPolicies"] = {k: v for k, v in (it.get("netPolicies") or {}).items()
                             if k in kept}
        src["layoutModules"] = [it]
    for name, pw, ph in PAPERS:
        if name == paper:
            src["sheet"] = {"minX": 0, "minY": 0, "maxX": pw, "maxY": ph}
            break
    src["maxCandidates"] = src.get("maxCandidates") or 1000000
    probe = pathlib.Path(tmp_dir) / ("confirm-%s-%s.json" % (module, paper))
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
    out = pathlib.Path(tmp_dir) / ("confirm-%s-%s-out.json" % (module, paper))
    p = subprocess.run([exe, "sch", "lib-layout", "--from", str(probe), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3600)
    msg = ((p.stdout or "") + (p.stderr or "")).strip()
    ok = out.is_file() and out.stat().st_size > 0
    return ok, msg[:200]


def main() -> int:
    ap = argparse.ArgumentParser(description="按实测包络规划页与纸型")
    ap.add_argument("--input", action="append", required=True,
                    help="lib-layout 输入（可多次给）")
    ap.add_argument("--out", help="写出 page-plan.json")
    ap.add_argument("--paper-floor", default="A4", choices=[p[0] for p in PAPERS])
    ap.add_argument("--confirm", action="store_true",
                    help="用真实 lib-layout 逐页确认（慢，但结论可信）")
    ap.add_argument("--exe", help="easycirq 可执行文件路径")
    ap.add_argument("--tmp-dir", default=".easycirq/page-confirm")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = []
    for path in args.input:
        p = pathlib.Path(path)
        if not p.is_file():
            print("找不到输入：%s" % p, file=sys.stderr)
            return 2
        src = load(p)
        for r in module_envelopes(src):
            r["source"] = str(p)
            rows.append(r)
    if not rows:
        print("输入里没有任何模块", file=sys.stderr)
        return 2

    pages = build_plan(rows, args.paper_floor)
    for pg in pages:
        r = next(x for x in rows if x["module"] == pg["module"])
        pg["source"] = r["source"]

    if args.confirm:
        exe = args.exe or str(pathlib.Path(
            __import__("os").environ.get("LOCALAPPDATA", "")) /
            "EasyCirq" / "bin" / "easycirq.exe")
        if not pathlib.Path(exe).is_file():
            print("找不到 easycirq，无法确认：%s" % exe, file=sys.stderr)
            return 2
        for pg in pages:
            # 从建议纸型起，逐级放大直到真的装得下（公式可能低估）
            start = ORDER.get(pg["suggestedPaper"] or "A4", 0)
            for name, _, _ in PAPERS[start:]:
                ok, msg = confirm_page(pg["source"], pg["module"], name,
                                       exe, args.tmp_dir)
                if ok:
                    pg["confirmedPaper"] = name
                    break
                pg["lastError"] = msg
            if not pg["confirmedPaper"]:
                pg["confirmedPaper"] = None

    doc = {
        "schema": SCHEMA,
        "rule": "一个模块一页；纸型先由估计包络给候选，再由真实运行确认",
        "margin": MARGIN,
        "widthFactor": WIDTH_FACTOR,
        "paperFloor": args.paper_floor,
        "confirmed": bool(args.confirm),
        "pages": pages,
    }
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")

    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print("页面规划（%d 页，一模块一页）" % len(pages))
        print("  %-4s %-22s %4s %8s  %-8s %s"
              % ("页", "图纸名（按模块）", "件数", "估计宽", "建议纸", "确认纸"))
        for pg in pages:
            print("  %-4s %-22s %4d %8.0f  %-8s %s"
                  % (pg["page"], pg.get("pageName") or pg["module"], pg["parts"],
                     pg["estWidth"], pg["suggestedPaper"] or "无",
                     pg["confirmedPaper"] or ("未确认" if not args.confirm else "**装不下**")))
        if args.confirm:
            bad = [p for p in pages if not p["confirmedPaper"]]
            if bad:
                print()
                print("  ⚠ %d 页连 A1 都装不下：%r —— 这些只能拆模块"
                      % (len(bad), [p["module"] for p in bad]))
        print()
        print("  提醒：建议纸型只用**估计**，可能低估（实测有小模块估 196 却装不进 A4）。")
        print("        要下定论请加 --confirm 跑一次真实 lib-layout。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
