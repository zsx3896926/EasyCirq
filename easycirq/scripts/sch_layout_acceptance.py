#!/usr/bin/env python3
"""原理图图面验收：把"能测的"和"测不了的"分开说清。

为什么需要它：直接跑 `sch_layout_check.py --strict` 会把两类东西混在
`blocking_findings` 里：

  1. **真几何缺陷** —— 越页、导线穿本体、模块框切器件：离线就能定论
  2. **缺证据的候选** —— 不同网络导线交叉（缺 host 无结点证据）、
     文字相压（缺渲染文字）：**离线判不了**，必须上机导出

混在一起报"115 项缺陷"，会让人以为图很糟；全都不报，又会让人以为都合格。
两者都是错的。

所以本脚本按判据分类，给每项三种结论之一：

  PASS      已测且无缺陷
  FAIL      已测且有缺陷（附对象）
  NOT RUN   缺证据，附**下一步要跑的命令**

用法：
  python scripts/sch_layout_acceptance.py --strict-input strict-M1.json \\
      --out acceptance-M1.json [--json]
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

# 判据 → 缺陷码。NOT RUN 的判据要写清缺什么证据。
CRITERIA = [
    {
        "id": "A_content_inside_page",
        "title": "内容不越框",
        "codes": ["outside_page"],
        "requires": ["components"],
        "needs": [],
    },
    {
        "id": "C_wire_vs_body",
        "title": "导线不穿器件本体",
        "codes": ["wire_enters_bbox"],
        "requires": ["components", "wires"],
        "needs": [],
    },
    {
        "id": "D_frame_vs_object",
        "title": "模块框不切器件/导线",
        "codes": ["frame_border_crosses_object"],
        "requires": ["components", "module_frames"],
        "needs": [],
    },
    {
        "id": "B_text_occlusion",
        "title": "遮字/文字相压",
        "codes": ["bbox_overlap"],
        # 只有拿到渲染文字（SVG）才能定论
        "needs": ["easycirq sch export-image --scope page --format svg",
                  "python scripts/svg_text_bbox.py page.svg"],
    },
    {
        "id": "E_label_anchor",
        "title": "标签落在真实端点、朝向一致",
        "codes": ["dangling_label", "label_net_mismatch",
                  "netflag_rotation_outlier"],
        "needs": ["easycirq sch read --page <P>（取 visible_text 与 junction）"],
    },
    {
        "id": "F_net_text",
        "title": "重复网名/孤立文字",
        "codes": ["duplicate_net_text", "unowned_visible_text"],
        "needs": ["easycirq sch export-image --scope page --format svg",
                  "python scripts/svg_text_bbox.py page.svg"],
    },
    {
        "id": "H_crossing_evidence",
        "title": "不同网络导线交叉无结点",
        "codes": ["different_named_wires_cross"],
        # 交叉本身在原理图上合法（Go 布线器只禁接触，不禁垂直跨越）；
        # 要定论必须有宿主给出的"此处无结点"证据。
        "needs": ["easycirq sch junction-report --page <P>",
                  "layout_from_easycirq.py --junction-report <报告>"],
    },
    {
        "id": "I_title_block",
        "title": "图签无重复文字",
        "codes": ["title_block_duplicate_text"],
        "requires": ["title_block"],
        "needs": ["easycirq sch sheet-geometry --from-svg page.svg"],
    },
    {
        "id": "G_zone_readability",
        "title": "分区阅读顺序",
        "codes": ["zone_reading_order"],
        "needs": ["--visible-text（分区标题文字）"],
    },
]


def find_checker() -> pathlib.Path:
    """优先用技能目录里的检查器；找不到就用仓库内同名脚本。"""
    home = pathlib.Path(os.environ.get("USERPROFILE") or pathlib.Path.home())
    for base in (home / ".agents" / "skills" / "easycirq" / "scripts",
                 home / ".claude" / "skills" / "easycirq" / "scripts"):
        p = base / "sch_layout_check.py"
        if p.is_file():
            return p
    here = pathlib.Path(__file__).resolve().parent
    return here / "sch_layout_check.py"


CORNER_TOL = 24.0          # 位号离本体角的允许距离（raw）


def _corner_label(box_c, box_t, content, designator):
    """文字内容 == 本器件位号，且中心贴近本体某个角 → 角标约定。"""
    if not designator or content != designator:
        return False
    cx = (box_t[0] + box_t[2]) / 2.0
    cy = (box_t[1] + box_t[3]) / 2.0
    for ax in (box_c[0], box_c[2]):
        for ay in (box_c[1], box_c[3]):
            if abs(cx - ax) <= CORNER_TOL and abs(cy - ay) <= CORNER_TOL:
                return True
    return False


def _reason_counts(items):
    out = {}
    for it in items:
        r = it.get("exempt_reason") or "unknown"
        out[r] = out.get(r, 0) + 1
    return out


def _pin_name_false_positives(findings, src, owners=None):
    """挑出"文字压在**自己**本体内且内容是该器件引脚名"的误报。

    返回 (kept, exempted)。判定条件全部显式：
      • 一条 finding 的两个对象里，一个是器件、一个是文字
      • 文字内容 == 该器件某个引脚名（大小写敏感，与 pinName 一致）
      • 文字锚点落在该器件 bbox 内
    """
    comps, texts = {}, {}
    for c in src.get("components") or []:
        cid = c.get("id")
        b = c.get("bbox")
        if isinstance(b, dict):
            b = [b["minX"], b["minY"], b["maxX"], b["maxY"]]
        if cid and b:
            desig = str(c.get("designator") or c.get("ref") or "")
            if not desig and owners:
                desig = str(owners.get(cid) or "")
            comps[cid] = (b, desig)
    for t in src.get("texts") or []:
        b = t.get("bbox")
        if isinstance(b, dict):
            b = [b["minX"], b["minY"], b["maxX"], b["maxY"]]
        if t.get("id") and b:
            texts[t["id"]] = (b, str(t.get("content") or "").strip())

    # 引脚点：id 末段是引脚名（如 "U3-EN" → "EN"），坐标是实测位置
    pins = []
    for ap in src.get("attachment_points") or []:
        if ap.get("kind") != "pin":
            continue
        aid = str(ap.get("id") or "")
        name = aid.rsplit("-", 1)[-1].strip()
        if name and ap.get("x") is not None:
            pins.append((ap["x"], ap["y"], name))

    kept, exempted = [], []
    for f in findings:
        objs = f.get("objects") or []
        if len(objs) != 2:
            kept.append(f)
            continue
        hit = False
        for a, b in (objs, list(reversed(objs))):
            if a not in comps or b not in texts:
                continue
            (box_c, designator) = comps[a]
            (box_t, content) = texts[b]
            cx = (box_t[0] + box_t[2]) / 2.0
            cy = (box_t[1] + box_t[3]) / 2.0
            inside = (box_c[0] <= cx <= box_c[2] and box_c[1] <= cy <= box_c[3])
            if not content:
                continue
            # 该器件框内必须有一个同名引脚点，才认作"它自己的引脚名"
            # 引脚点在**本体外**（引脚线段伸出框），所以要给一个外扩余量。
            # 实测 U3 的 EN 引脚在 (240,150)，而本体从 x=250 开始。
            m = 40.0
            pin_inside = inside and any(
                name == content
                and box_c[0] - m <= px <= box_c[2] + m
                and box_c[1] - m <= py <= box_c[3] + m
                for px, py, name in pins)
            if pin_inside:
                hit = "pin_name_inside_body"
                break
            if _corner_label(box_c, box_t, content, designator):
                hit = "designator_at_corner"
                break
        if hit and f.get("code") in ("bbox_overlap", "wire_enters_bbox"):
            f = dict(f)
            f["exempt_reason"] = hit
            exempted.append(f)
        else:
            kept.append(f)
    return kept, exempted


def _covered(key, coverage):
    """该覆盖项是否真的存在（complete 或 observed>0）。"""
    if key == "title_block":
        # 图签不在 coverage 里；由 evaluate 单独注入，缺了就按未覆盖处理
        return bool(coverage.get("_title_block"))
    item = coverage.get(key) or {}
    if item.get("status") == "complete":
        return True
    return int(item.get("observed") or 0) > 0


def evaluate(strict_input, out_path, checker=None, owners=None):
    checker = checker or find_checker()
    rep = pathlib.Path(str(out_path)).with_suffix(".check.json")
    p = subprocess.run([sys.executable, str(checker), str(strict_input),
                        "--strict", "--out", str(rep)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if not rep.is_file():
        raise SystemExit("验收检查未产出：%s"
                         % (((p.stdout or "") + (p.stderr or ""))[:400],))
    data = json.loads(rep.read_text(encoding="utf-8"))
    try:
        src = json.loads(pathlib.Path(strict_input).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        src = {}
    if (src.get("title_block") or src.get("titleBlock")
            or (src.get("sheet") or {}).get("title_block")):
        data.setdefault("coverage", {})["_title_block"] = True
    findings = list(data.get("blocking_findings") or [])
    findings += list(data.get("informational_findings") or [])
    coverage = data.get("coverage") or {}

    findings, exempted = _pin_name_false_positives(findings, src, owners)

    by_code = {}
    for f in findings:
        by_code.setdefault(f.get("code"), []).append(f)

    rows = []
    for c in CRITERIA:
        hits = []
        for code in c["codes"]:
            hits += by_code.get(code) or []
        if hits:
            why = {(h.get("detail") or "")[:60] for h in hits}
            status = "FAIL"
            # 全是"缺证据"类候选 → 记 NOT RUN，不冒充缺陷
            if all((h.get("status") == "review_candidate"
                    and "no host" in str(h.get("detail") or "")) for h in hits):
                status = "NOT RUN"
            rows.append({"id": c["id"], "title": c["title"], "status": status,
                         "count": len(hits), "needs": c["needs"],
                         "samples": [h.get("objects") for h in hits[:3]],
                         "detail": sorted(why)[:2]})
        else:
            # 没有 finding：如果该判据依赖的证据本身缺失 → NOT RUN，不是 PASS
            need = c["needs"]
            if c["id"] in ("B_text_occlusion", "F_net_text", "G_zone_readability") \
                    and (coverage.get("texts") or {}).get("status") != "complete":
                rows.append({"id": c["id"], "title": c["title"],
                             "status": "NOT RUN", "count": 0, "needs": need,
                             "samples": [],
                             "detail": ["文字覆盖 %s，无渲染文字"
                                        % (coverage.get("texts") or {}).get("status")]})
            elif c["id"] == "E_label_anchor" \
                    and (coverage.get("label_anchors") or {}).get("observed", 0) == 0:
                rows.append({"id": c["id"], "title": c["title"],
                             "status": "NOT RUN", "count": 0, "needs": need,
                             "samples": [], "detail": ["标签锚点覆盖为 0"]})
            else:
                # **没有数据不许判 PASS。** 缺覆盖就是没测，记 NOT RUN。
                lacking = [k for k in (c.get("requires") or [])
                           if not _covered(k, coverage)]
                if lacking:
                    rows.append({"id": c["id"], "title": c["title"],
                                 "status": "NOT RUN", "count": 0,
                                 "needs": c["needs"],
                                 "samples": [],
                                 "detail": ["覆盖缺口：%s" % ", ".join(lacking)]})
                else:
                    rows.append({"id": c["id"], "title": c["title"],
                                 "status": "PASS", "count": 0, "needs": [],
                                 "samples": [], "detail": []})

    verdict = "BLOCKED" if any(r["status"] == "FAIL" for r in rows) else (
        "INCOMPLETE" if any(r["status"] == "NOT RUN" for r in rows) else "PASS")
    report = {"schema": "easycirq-sch-acceptance/v1",
              "strictInput": str(strict_input),
              "checkerVerdict": data.get("status"),
              "verdict": verdict,
              "criteria": rows,
              "knownFalsePositives": {
                  "count": len(exempted),
                  "byReason": _reason_counts(exempted),
                  "reason": "文字落在其**所属器件**本体内且内容是该器件的引脚名"
                            "（箱形符号把引脚名画在框内属正常画法）；"
                            "适配器的 owner 豁免分支到不了 pagePrimitives.texts 通道，"
                            "故在此显式记录为误报",
                  "codes": sorted({f.get("code") for f in exempted}),
                  "samples": [f.get("objects") for f in exempted[:3]],
              },
              "coverage": coverage}
    pathlib.Path(out_path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def render(report):
    icon = {"PASS": "✅", "FAIL": "❌", "NOT RUN": "⛔"}
    lines = ["  %-4s %-26s %-8s %s" % ("", "判据", "结论", "说明")]
    for r in report["criteria"]:
        note = ""
        if r["status"] == "FAIL":
            note = "%d 项，例 %s" % (r["count"], r["samples"][0] if r["samples"] else "")
        elif r["status"] == "NOT RUN":
            note = ("缺证据：" + (r["detail"][0] if r["detail"] else "")
                    + ("；下一步 " + r["needs"][0] if r.get("needs") else ""))
        lines.append("  %-4s %-26s %-8s %s"
                     % (icon[r["status"]], r["title"], r["status"], note))
    fp = report.get("knownFalsePositives") or {}
    if fp.get("count"):
        lines.append("  已知误报 %d 项 %s"
                     % (fp["count"], json.dumps(fp.get("byReason") or {},
                                                ensure_ascii=False)))
    lines.append("")
    lines.append("  判定：%s（检查器：%s）"
                 % (report["verdict"], report["checkerVerdict"]))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="原理图图面验收（分开报 真缺陷 / 缺证据）")
    ap.add_argument("--strict-input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--checker", help="sch_layout_check.py 路径")
    ap.add_argument("--owners",
                    help="JSON：{器件id: 位号}。缺了就跳过位号角标判定（不误豁免）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    owners = None
    if args.owners:
        owners = json.loads(pathlib.Path(args.owners).read_text(encoding="utf-8"))
    rep = evaluate(args.strict_input, args.out,
                   pathlib.Path(args.checker) if args.checker else None, owners)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render(rep))
    return 0 if rep["verdict"] == "PASS" else (2 if rep["verdict"] == "BLOCKED" else 1)


if __name__ == "__main__":
    sys.exit(main())
