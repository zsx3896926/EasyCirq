#!/usr/bin/env python3
"""生成**可审计的状态汇总**：目标每条要求 → 状态 → 复现命令 → 证据文件。

为什么要有它：
  · 判据结果散在 5 个 JSON、3 个脚本、一堆中间文件里
  · 目标明确要求"每项判据都要有**可复现的测量命令**"
  · 手写状态会过期（#89 就栽在"旧产物冒充当前结论"）

所以：**状态由脚本从产物算出来**，并且对**陈旧产物**判 STALE 而不是照抄。
任何人跑一次就能核对，不需要相信我的话。

用法：
  python scripts/sch_preview_status.py --work reports/hard-board/board2
  python scripts/sch_preview_status.py --work ... --out STATUS.md
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

MODULES = ("M1", "M2", "M3", "M4", "M5")
ICON = {"PASS": "✅", "FAIL": "❌", "NOT RUN": "⛔", "N/A": "➖", "STALE": "🕒"}

# 目标点名的判据 → 对应验收 ID
OBJECTIVE = [
    ("内容不越框", "A_content_inside_page"),
    ("导线不穿器件本体", "C_wire_vs_body"),
    ("模块框不切器件/导线", "D_frame_vs_object"),
    ("遮字 / 文字相压", "B_text_occlusion"),
    ("标签落在真实端点、朝向一致", "E_label_anchor"),
    ("网标朝向一致", "J_netflag_rotation"),
    ("重复网名 / 孤立文字", "F_net_text"),
    ("不同网络导线交叉无结点", "H_crossing_evidence"),
    ("图签无重复文字", "I_title_block"),
    ("分区阅读顺序", "G_zone_readability"),
]


def skill_scripts() -> pathlib.Path:
    return pathlib.Path(os.environ.get("USERPROFILE") or pathlib.Path.home()) \
        .joinpath(".agents", "skills", "easycirq", "scripts")


def stale(artifact: pathlib.Path, ref: pathlib.Path) -> bool:
    try:
        return artifact.stat().st_mtime < ref.stat().st_mtime
    except OSError:
        return True


def load(p: pathlib.Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def collect(work: pathlib.Path):
    out = {}
    for m in MODULES:
        comp = work / ("composition-%s-placed.json" % m)
        acc_p = work / ("acceptance-%s.json" % m)
        d = load(acc_p)
        if not d:
            out[m] = {"status": "STALE", "why": "无验收产物"}
            continue
        if comp.is_file() and stale(acc_p, comp):
            out[m] = {"status": "STALE", "why": "产物早于排版稿"}
            continue
        out[m] = {"status": "OK", "report": d}
    return out


def direct_checks(work: pathlib.Path, sk: pathlib.Path):
    """直接跑技能自带的两个检查器（不经我的封装）。"""
    res = {}
    for m in MODULES:
        strict = work / ("strict-%s-full.json" % m)
        comp = work / ("composition-%s-placed.json" % m)
        row = {"checker": None, "text": None, "stale": False}
        # 输入本身可能陈旧：`strict-*` 早于排版稿就是旧结论（M1 曾报 blocking 113）
        if strict.is_file() and comp.is_file() and stale(strict, comp):
            row["stale"] = True
            res[m] = row
            continue
        if strict.is_file():
            p = subprocess.run([sys.executable, str(sk / "sch_layout_check.py"),
                                str(strict), "--strict"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1800)
            if p.stdout.strip():
                try:
                    d = json.loads(p.stdout)
                    row["checker"] = {"status": d.get("status"),
                                      "blocking": len(d.get("blocking_findings") or [])}
                except ValueError:
                    row["checker"] = {"status": "unparseable", "blocking": -1}
        ain = work / ("visible-%s.audit.json" % m)
        if ain.is_file():
            tmp = work / ("_status_audit-%s.json" % m)
            tmp.unlink(missing_ok=True)
            subprocess.run([sys.executable, str(sk / "sch_text_audit.py"),
                            str(ain), "--strict", "--out", str(tmp)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
            d = load(tmp) if tmp.is_file() else None
            if d:
                row["text"] = {"measured": d.get("measured_count"),
                               "findings": len(d.get("findings") or [])}
            tmp.unlink(missing_ok=True)
        res[m] = row
    return res


def build(work: pathlib.Path) -> str:
    sk = skill_scripts()
    data = collect(work)
    direct = direct_checks(work, sk)

    L = ["# 原理图预览 · 可审计状态汇总", ""]
    L.append("> 由 `sch_preview_status.py` 从**真实产物**算出，不是手填。")
    L.append("> 产物早于对应排版稿即判 🕒 STALE，按 NOT RUN 处理。")
    L.append("")

    L.append("## 目标判据 → 状态")
    L.append("")
    hdr = "| 判据 | " + " | ".join(MODULES) + " |"
    L.append(hdr)
    L.append("|" + "---|" * (len(MODULES) + 1))
    for title, cid in OBJECTIVE:
        cells = []
        for m in MODULES:
            row = data[m]
            if row["status"] != "OK":
                cells.append(ICON["STALE"])
                continue
            c = next((x for x in row["report"]["criteria"] if x["id"] == cid), None)
            cells.append(ICON.get(c["status"], c["status"]) if c else "—")
        L.append("| %s | %s |" % (title, " | ".join(cells)))
    L.append("")

    L.append("## 直接跑技能自带检查器（不经封装）")
    L.append("")
    L.append("| 模块 | sch_layout_check --strict | sch_text_audit --strict |")
    L.append("|---|---|---|")
    for m in MODULES:
        r = direct[m]
        if r.get("stale"):
            ck = tx = "🕒 输入陈旧"
        else:
            ck = "NOT RUN" if not r["checker"] else \
                "%s（blocking %d）" % (r["checker"]["status"], r["checker"]["blocking"])
            tx = "NOT RUN" if not r["text"] else \
                "实测 %s / 缺陷 %d" % (r["text"]["measured"], r["text"]["findings"])
        L.append("| %s | %s | %s |" % (m, ck, tx))
    L.append("")

    bad = [m for m in MODULES if data[m]["status"] != "OK"]
    if bad:
        L.append("## 🕒 无有效结论的模块")
        L.append("")
        for m in bad:
            L.append("- **%s**：%s —— 需重跑流水线" % (m, data[m]["why"]))
        L.append("")

    L.append("## 复现命令")
    L.append("")
    L.append("```bash")
    L.append("# 全链：排版 → 归位 → 出图 → 渲染 → 实测文字 → 严格检查 → 验收")
    L.append("python scripts/sch_preview_accept.py --work %s" % work)
    L.append("# 本汇总")
    L.append("python scripts/sch_preview_status.py --work %s" % work)
    L.append("```")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成可审计状态汇总")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    work = pathlib.Path(args.work)
    text = build(work)
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print("  状态汇总 → %s" % args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
