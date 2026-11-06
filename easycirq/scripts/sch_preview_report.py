#!/usr/bin/env python3
"""生成**一页纸验收报告**（Markdown）：五块的判据表 + 复现命令 + 缺口清单。

为什么需要它：判据结果散在 5 个 JSON、3 个脚本、一堆中间文件里。
要"可复现的测量命令"，就得有一份把**结论、证据、复现方式**放一起的东西，
而不是让人自己去翻目录。

内容全部来自本轮**真实执行**的产物：
  acceptance-<M>.json（sch_layout_acceptance.py 的输出）
  textaudit-<M>.json（sch_text_audit.py 的输出）

用法：
  python scripts/sch_preview_report.py --work reports/hard-board/board2 \\
      --out reports/hard-board/board2/ACCEPTANCE.md
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ICON = {"PASS": "✅", "FAIL": "❌", "NOT RUN": "⛔", "N/A": "➖"}
MODULES = ("M1", "M2", "M3", "M4", "M5")


def load(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build(work):
    work = pathlib.Path(work)
    rows = {}
    for m in MODULES:
        d = load(work / ("acceptance-%s.json" % m))
        if not d:
            continue
        rows[m] = d
    if not rows:
        raise SystemExit("没有 acceptance-*.json —— 先跑 sch_preview_accept.py")

    first = next(iter(rows.values()))
    crit = [c["id"] for c in first["criteria"]]
    titles = {c["id"]: c["title"] for c in first["criteria"]}

    lines = ["# 原理图预览 · 图面验收报告", ""]
    lines.append("> 由 `sch_preview_report.py` 从真实执行产物生成；"
                 "表格里每个状态都能用下方命令复现。")
    lines.append("")

    lines.append("## 判据总表")
    lines.append("")
    head = "| 判据 | " + " | ".join(rows) + " |"
    lines.append(head)
    lines.append("|" + "---|" * (len(rows) + 1))
    for cid in crit:
        cells = []
        for m in rows:
            c = next(x for x in rows[m]["criteria"] if x["id"] == cid)
            cells.append(ICON.get(c["status"], c["status"]))
        lines.append("| %s | %s |" % (titles[cid], " | ".join(cells)))
    lines.append("")

    lines.append("## 逐块统计")
    lines.append("")
    lines.append("| 模块 | 判定 | 通过 | 失败 | 缺证据 | 不适用 | 已知误报 |")
    lines.append("|---|---|---|---|---|---|---|")
    for m, d in rows.items():
        cs = d["criteria"]
        cnt = lambda s: sum(1 for c in cs if c["status"] == s)
        fp = (d.get("knownFalsePositives") or {}).get("count", 0)
        lines.append("| %s | %s | %d | %d | %d | %d | %d |"
                     % (m, d["verdict"], cnt("PASS"), cnt("FAIL"),
                        cnt("NOT RUN"), cnt("N/A"), fp))
    lines.append("")

    lines.append("## 未通过 / 未测 / 不适用（逐条）")
    lines.append("")
    for cid in crit:
        bad = [(m, next(x for x in rows[m]["criteria"] if x["id"] == cid))
               for m in rows]
        bad = [(m, c) for m, c in bad if c["status"] != "PASS"]
        if not bad:
            continue
        m0, c0 = bad[0]
        lines.append("### %s — %s" % (titles[cid], ICON.get(c0["status"])))
        lines.append("")
        if c0.get("detail"):
            lines.append("理由：%s" % "；".join(c0["detail"]))
            lines.append("")
        if c0.get("needs"):
            lines.append("下一步：`%s`" % c0["needs"][0])
            lines.append("")
        if c0["status"] == "FAIL":
            lines.append("涉及模块：%s（各 %d 项）"
                         % ("、".join(m for m, _ in bad),
                            c0["count"]))
            if c0.get("samples"):
                lines.append("样例：`%s`" % c0["samples"][0])
            lines.append("")

    lines.append("## 复现命令")
    lines.append("")
    lines.append("```bash")
    lines.append("# 一条命令跑完整条链（排版稿 → 渲染 → 实测文字 → 严格检查 → 验收）")
    lines.append("python scripts/sch_preview_accept.py --work %s" % work)
    lines.append("")
    lines.append("# 文字审计（独立一项判据）")
    lines.append("python scripts/sch_preview_textaudit.py --texts %s/texts-M3.json \\"
                 % work)
    lines.append("    --visible %s/visible-M3.json --out %s/visible-M3.audit.json"
                 % (work, work))
    lines.append("python <skill>/scripts/sch_text_audit.py "
                 "%s/visible-M3.audit.json --strict" % work)
    lines.append("")
    lines.append("# 本报告")
    lines.append("python scripts/sch_preview_report.py --work %s" % work)
    lines.append("```")
    lines.append("")

    lines.append("## 已知误报（不计入失败）")
    lines.append("")
    seen = {}
    for m, d in rows.items():
        for k, v in ((d.get("knownFalsePositives") or {}).get("byReason") or {}).items():
            seen[k] = seen.get(k, 0) + v
    for k, v in sorted(seen.items()):
        if k == "pin_name_inside_body":
            lines.append("- **引脚名画在自己本体内**：%d 项 —— 箱形符号的正常画法" % v)
        elif k == "designator_at_corner":
            lines.append("- **位号贴在本体角上**：%d 项 —— 预览渲染器的排版约定" % v)
        else:
            lines.append("- %s：%d 项" % (k, v))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成一页纸验收报告")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", help="默认写到 <work>/ACCEPTANCE.md")
    args = ap.parse_args()
    work = pathlib.Path(args.work)
    out = pathlib.Path(args.out) if args.out else work / "ACCEPTANCE.md"
    text = build(work)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print("  验收报告 → %s（%d 行）" % (out, text.count("\n") + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
