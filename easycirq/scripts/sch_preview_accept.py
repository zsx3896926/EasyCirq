#!/usr/bin/env python3
"""一条命令跑完整图面验收链（多块），输出诚实的判据表。

链路（每一步都可单独复现）：

    排版稿(已归位) → sch_preview_zones → easycirq sch layout-render → SVG
      → svg_text_bbox.py（实测文字边界）→ sch_preview_text（还原页坐标）
      → sch_composition_snapshot --text-plan → layout_from_easycirq.py
      → sch_layout_check.py --strict → sch_layout_acceptance.py（分类结论）

为什么这么绕：排版稿**不带文字几何**，自己造文字会产出假缺陷（#59）；
只有渲染器画出来的文字才是真几何，而它和器件的坐标系要靠 SVG 里的
图纸边框矩形换算（#61）。

用法：
  python scripts/sch_preview_accept.py --work reports/hard-board/board2 \\
      --modules M1,M2,M3,M4,M5
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

HERE = pathlib.Path(__file__).resolve().parent
PAD_FRAME = 400.0          # 渲染框外扩（要包住渲染器认定的全部内容）


def skill_scripts() -> pathlib.Path:
    home = pathlib.Path(os.environ.get("USERPROFILE") or pathlib.Path.home())
    for base in (home / ".agents" / "skills" / "easycirq" / "scripts",
                 home / ".claude" / "skills" / "easycirq" / "scripts"):
        if (base / "layout_from_easycirq.py").is_file():
            return base
    raise SystemExit("找不到技能脚本目录（layout_from_easycirq.py）")


def exe_path() -> pathlib.Path:
    base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home())
    return pathlib.Path(base) / "EasyCirq" / "bin" / "easycirq.exe"


def run_py(cmd, timeout=1800):
    return subprocess.run([sys.executable] + [str(c) for c in cmd],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def widen(zones_path, page):
    """把渲染用的图纸与模块框放大，使渲染器认可"框包住全部内容"。"""
    z = json.loads(pathlib.Path(zones_path).read_text(encoding="utf-8"))
    b = {"minX": page["minX"] - 800, "minY": page["minY"] - 800,
         "maxX": page["maxX"] + 1200, "maxY": page["maxY"] + 900}
    z["sheet"]["bounds"] = dict(b)
    z["sheet"]["border"] = dict(b)
    for zone in z["zones"]:
        r = (zone.get("frame") or {}).get("rect")
        if not r:
            continue
        cx, cy = (r["minX"] + r["maxX"]) / 2.0, (r["minY"] + r["maxY"]) / 2.0
        hw = (r["maxX"] - r["minX"]) / 2.0 + PAD_FRAME
        hh = (r["maxY"] - r["minY"]) / 2.0 + PAD_FRAME
        r2 = {"minX": cx - hw, "minY": cy - hh, "maxX": cx + hw, "maxY": cy + hh}
        zone["frame"]["rect"] = r2
        zone["frame"]["titleX"] = r2["minX"] + 4
        zone["frame"]["titleY"] = r2["maxY"] - 4
        zone["sheetPosition"] = {"x": (r2["minX"] // 5) * 5,
                                 "y": (r2["maxY"] // 5) * 5}
    pathlib.Path(zones_path).write_text(
        json.dumps(z, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return z


def one(module, work, exe, sk, verbose=True):
    work = pathlib.Path(work)
    comp = work / ("composition-%s-placed.json" % module)
    if not comp.is_file():
        return {"module": module,
                "error": "缺 %s（先跑 sch_layout_normalize.py）" % comp.name}
    page = json.loads(comp.read_text(encoding="utf-8")).get("sheet")
    if not page:
        return {"module": module, "error": "排版稿没有 sheet"}

    zones = work / ("zones-%s.json" % module)
    r = run_py([HERE / "sch_preview_zones.py", comp, zones])
    if not zones.is_file():
        return {"module": module, "error": "zones 生成失败：%s" % (r.stderr or "")[:200]}
    widen(zones, page)

    svg = work / ("preview-%s.svg" % module)
    svg.unlink(missing_ok=True)
    p = subprocess.run([str(exe), "sch", "layout-render", "--from", str(zones),
                        "--out", str(svg)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    if not svg.is_file():
        return {"module": module,
                "error": "渲染失败：%s" % ((p.stdout or p.stderr or "").strip()[:200])}

    text_json = work / ("text-%s.json" % module)
    r = run_py([sk / "svg_text_bbox.py", svg, "--out", text_json])
    texts = work / ("texts-%s.json" % module)
    visible = work / ("visible-%s.json" % module)
    pb = "%g,%g,%g,%g" % (page["minX"], page["minY"], page["maxX"], page["maxY"])
    r = run_py([HERE / "sch_preview_text.py", "--svg", svg, "--zones", zones,
                "--measure", text_json, "--out-texts", texts,
                "--out-visible", visible, "--page-bounds", pb])
    if not texts.is_file():
        return {"module": module, "error": "文字换算失败：%s" % (r.stderr or "")[:200]}

    snap = work / ("snap-%s-full" % module)
    run_py([HERE / "sch_composition_snapshot.py", "--composition", comp,
            "--out-dir", snap, "--text-plan", texts])

    # 网标朝向一致性：每个网络取标记朝向的**众数**作为期望值。
    # 只有 ≥2 个标记的网络才判"是否一致"（一个标记谈不上一致性）。
    rot_policy = {}
    try:
        snap_doc = json.loads((snap / "list.json").read_text(encoding="utf-8"))
        by_net = {}
        for c in (snap_doc.get("result") or {}).get("components") or []:
            if c.get("componentType") != "netflag":
                continue
            net, rot = c.get("net"), c.get("rotation")
            if net and rot is not None:
                by_net.setdefault(net, []).append(int(rot))
        for net, rots in by_net.items():
            if len(rots) < 2:
                continue
            counts = {}
            for r in rots:
                counts[r] = counts.get(r, 0) + 1
            best = max(counts, key=lambda k: counts[k])
            if counts[best] * 2 > len(rots):        # 有明显众数才立判据
                rot_policy[net] = best
    except (OSError, ValueError):
        rot_policy = {}

    strict = work / ("strict-%s-full.json" % module)
    strict.unlink(missing_ok=True)
    acmd = [sk / "layout_from_easycirq.py", "--list", snap / "list.json",
            "--visible-text", visible, "--rendered-text", text_json,
            "--out", strict]
    # 图签：把 zones 里的 titleBlock 矩形交给适配器，
    # 它据此把框内文字标为 title_block，并置覆盖为 complete。
    # 少了这一步，"图签无重复文字"只能一直是 N/A。
    try:
        tbz = json.loads((work / ("zones-%s.json" % module)).read_text(encoding="utf-8"))
        tb_rect = (tbz.get("sheet") or {}).get("titleBlock")
        if tb_rect:
            geo = work / ("sheet-geometry-%s.json" % module)
            geo.write_text(json.dumps({"titleBlock": {"bbox": tb_rect}},
                                      ensure_ascii=False), encoding="utf-8")
            acmd += ["--sheet-geometry", geo]
    except (OSError, ValueError):
        pass

    for net, deg in rot_policy.items():
        acmd += ["--expect-rotation", "%s=%d" % (net, deg)]
    run_py(acmd)

    # 按**几何**补登记图签归属：适配器给的 title_block_owned 可能是空的
    # （它按渲染行打标，id 命名空间与 page_texts 不一定对齐）。
    # 框心落在图签矩形内的文字，就属于图签。
    try:
        if tb_rect:
            doc = json.loads(pathlib.Path(strict).read_text(encoding="utf-8"))
            owned = []
            for t in doc.get("texts") or []:
                b = t.get("bbox")
                if not b:
                    continue
                cx = (b[0] + b[2]) / 2.0
                cy = (b[1] + b[3]) / 2.0
                if (tb_rect["minX"] <= cx <= tb_rect["maxX"]
                        and tb_rect["minY"] <= cy <= tb_rect["maxY"]):
                    t["kind"] = "title_block"
                    owned.append(t["id"])
            if owned:
                doc["title_block_owned"] = sorted(set(doc.get("title_block_owned") or [])
                                                   | set(owned))
                pathlib.Path(strict).write_text(
                    json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError, UnboundLocalError):
        pass

    if not strict.is_file():
        return {"module": module, "error": "严格输入生成失败"}
    src = json.loads(strict.read_text(encoding="utf-8"))

    # 器件 id → 位号（"位号写在角上"这条判定需要，缺了就不豁免）
    owners = None
    try:
        comp_doc = json.loads(comp.read_text(encoding="utf-8"))
        mods = comp_doc.get("modules") or [{}]
        pairs = {pl.get("primitiveId"): pl.get("designator")
                 for pl in (mods[0].get("placements") or [])}
        owners = work / ("owners-%s.json" % module)
        owners.write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    except (OSError, ValueError):
        owners = None

    out = work / ("acceptance-%s.json" % module)
    acmd = [HERE / "sch_layout_acceptance.py", "--strict-input", strict,
            "--out", out, "--json"]
    if owners is not None:
        acmd += ["--owners", owners]
    run_py(acmd)
    if not out.is_file():
        return {"module": module, "error": "验收未产出"}
    rep = json.loads(out.read_text(encoding="utf-8"))
    if verbose:
        txts = src.get("texts") or []
        measured = sum(1 for t in txts if t.get("measurement") == "bbox")
        print("  %-3s 文字 %2d（实测 %2d）  → %s"
              % (module, len(txts), measured, rep["verdict"]))
    return {"module": module, "verdict": rep["verdict"],
            "criteria": rep["criteria"],
            "knownFalsePositives": rep.get("knownFalsePositives") or {},
            "coverage": rep.get("coverage") or {}}


def main() -> int:
    ap = argparse.ArgumentParser(description="图面验收全链（多块）")
    ap.add_argument("--work", required=True)
    ap.add_argument("--modules", default="M1,M2,M3,M4,M5")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exe, sk = exe_path(), skill_scripts()
    if not exe.is_file():
        raise SystemExit("找不到 easycirq 可执行文件：%s" % exe)

    results = []
    for m in [x.strip() for x in args.modules.split(",") if x.strip()]:
        results.append(one(m, args.work, exe, sk))

    rows = [r for r in results if "criteria" in r]
    if rows:
        ids = [c["id"] for c in rows[0]["criteria"]]
        print()
        print("  判据".ljust(30) + "".join("%-6s" % r["module"] for r in rows))
        for cid in ids:
            title = next(c["title"] for c in rows[0]["criteria"] if c["id"] == cid)
            line = "  " + title.ljust(28)
            for r in rows:
                c = next(x for x in r["criteria"] if x["id"] == cid)
                st = c["status"]
                line += "%-6s" % ("PASS" if st == "PASS"
                                  else ("FAIL" if st == "FAIL"
                                        else ("N/A" if st == "N/A" else "N/R")))
            print(line)
        print()
        for r in results:
            if "error" in r:
                print("  %-3s ⛔ %s" % (r["module"], r["error"]))
                continue
            cs = r["criteria"]
            p = sum(1 for c in cs if c["status"] == "PASS")
            f = sum(1 for c in cs if c["status"] == "FAIL")
            n = sum(1 for c in cs if c["status"] == "NOT RUN")
            na = sum(1 for c in cs if c["status"] == "N/A")
            fp = (r["knownFalsePositives"] or {}).get("count", 0)
            print("  %-3s %-11s 通过 %d 失败 %d 缺证据 %d 不适用 %d 已知误报 %d"
                  % (r["module"], r["verdict"], p, f, n, na, fp))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r.get("verdict") == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
