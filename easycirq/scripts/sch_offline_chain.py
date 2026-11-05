#!/usr/bin/env python3
"""离线链一条命令：S1 规格 → 网表 → 引脚几何 → 页面规划 → 输入预检。

没有它的时候，这条路是**七个脚本手工串**，每步的产物路径都要记，
错一步就到下一步才炸（实测因此绕了很多弯路）。这条命令把顺序固定下来，
并且**每步都报告状态与下一步**，任一步失败就停在那里。

    S1  规格自检        sch_spec_check.py      （含选型可用性）
    S2  规范网表        sch_spec_netlist.py
    S3  引脚几何        sch_measure_parts.py   （离线度量，只读库）
    S4  页面规划        sch_page_plan.py       （按实测包络定页/定纸）
    S5  输入装配        sch_layout_input.py    （按页裁切）
    S6  两道预检        sch_module_fit.py + sch_layout_precheck.py

**不碰画布。** 全程只读库与本地文件（`lib symbol export-source` 是只读 API）。
真正落图是 `sch lib-layout` → `sch compose` 之后的事。

退出码：0 = 全链通过；1 = 某一步没过（会指出是哪一步、下一步做什么）。
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

HERE = pathlib.Path(__file__).resolve().parent


def run(script: str, args: list[str], timeout: int = 3600):
    cmd = [sys.executable, str(HERE / script)] + args
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def tail(text: str, n: int = 3) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return " | ".join(l.strip()[:110] for l in lines[-n:])


class Stage:
    def __init__(self, name: str):
        self.name = name
        self.ok = None
        self.detail = ""
        self.next = ""


def main() -> int:
    ap = argparse.ArgumentParser(description="离线链：S1 规格 → 预检通过")
    ap.add_argument("--spec", required=True, help="S1 的 spec.json")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--standard-parts",
                    default=str(HERE.parent / "references" / "standard-parts.json"))
    ap.add_argument("--blocks-dir", default="runtime/internal/blocks/data")
    ap.add_argument("--part-audit", help="已有的选型审计报告（可省，省了 S1 不查可用性）")
    ap.add_argument("--pages", help="只做这些页（逗号分隔，如 P1,P2）；默认做 spec 里的全部")
    ap.add_argument("--confirm-paper", action="store_true",
                    help="页面规划用真实 lib-layout 确认纸型（慢，但结论可信）")
    ap.add_argument("--exe", help="easycirq 可执行文件（--confirm-paper 需要）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stages: list[Stage] = []
    spec = pathlib.Path(args.spec)
    if not spec.is_file():
        print("找不到 spec：%s" % spec, file=sys.stderr)
        return 2
    spec_doc = json.loads(spec.read_text(encoding="utf-8"))
    page_ids = spec_doc.get("pages") or {}
    want = ([p.strip() for p in args.pages.split(",") if p.strip()]
            if args.pages else sorted(page_ids))

    # ── S1 规格自检（含选型可用性）────────────────────────────────────
    st = Stage("S1 规格自检")
    sargs = [str(spec), "--blocks-dir", args.blocks_dir]
    if args.part_audit:
        sargs += ["--audit", args.part_audit]
    code, txt = run("sch_spec_check.py", sargs)
    st.ok = code == 0
    st.detail = tail(txt, 2) if code == 0 else tail(txt, 4)
    st.next = "" if st.ok else "按提示修 spec（选型不可用要换料，别等 S3）"
    stages.append(st)
    if not st.ok:
        return report(stages, args.json)

    # ── S2 规范网表 ──────────────────────────────────────────────────
    st = Stage("S2 规范网表")
    netlist = out / "netlist.json"
    code, txt = run("sch_spec_netlist.py",
                    [str(spec), "--blocks-dir", args.blocks_dir,
                     "--out", str(netlist)])
    st.ok = code == 0
    st.detail = tail(txt, 3)
    st.next = "" if st.ok else "看 issues：NC 与连接冲突、块内引用不存在等"
    stages.append(st)
    if not st.ok:
        return report(stages, args.json)

    # ── S3 引脚几何（离线，只读库）─────────────────────────────────────
    st = Stage("S3 引脚几何")
    meas = out / "measurements.json"
    code, txt = run("sch_measure_parts.py",
                    ["--netlist", str(netlist),
                     "--standard-parts", args.standard_parts,
                     "--out", str(meas)], timeout=7200)
    st.ok = code == 0
    st.detail = tail(txt, 2)
    st.next = "" if st.ok else "失败的型号先跑 sch_part_audit.py 看是不是库记录读不出来"
    stages.append(st)
    if not st.ok:
        return report(stages, args.json)

    # ── S4 页面规划 ──────────────────────────────────────────────────
    st = Stage("S4 页面规划")
    st.ok = True
    st.detail = "稍后按页装配完再算（需要每页的输入）"
    stages.append(st)

    # ── S5 逐页装配输入 ───────────────────────────────────────────────
    st = Stage("S5 输入装配")
    style_plans = []
    for sp in sorted(out.glob("style-plan-*.json")):
        style_plans.append(str(sp))
    if not style_plans:
        st.ok = False
        st.detail = "out-dir 里没有 style-plan-*.json（S2 的产物要在这一步之前放进同一目录）"
        st.next = "先跑 sch_style_plan_check.py 出风格门报告，并把 style-plan 放到 out-dir"
        stages.append(st)
        return report(stages, args.json)

    inputs = {}
    failures = []
    for page in want:
        dest = out / ("layout-input-%s.json" % page)
        cargs = ["--netlist", str(netlist), "--measurements", str(meas),
                 "--page", page, "--out", str(dest)]
        for sp in style_plans:
            cargs += ["--style-plan", sp]
        code, txt = run("sch_layout_input.py", cargs)
        if code == 0 and dest.is_file():
            inputs[page] = dest
        else:
            failures.append((page, tail(txt, 2)))
    st.ok = not failures
    st.detail = ("%d 页装配成功" % len(inputs)) if st.ok else \
        "；".join("%s: %s" % (p, d) for p, d in failures[:2])
    st.next = "" if st.ok else "多为页 uuid 未在 spec.pages 里登记，或缺 measurements"
    stages.append(st)
    if not st.ok:
        return report(stages, args.json)

    # ── S4（补）页面规划 ─────────────────────────────────────────────
    st = stages[-2]
    plan = out / "page-plan.json"
    pargs = []
    for d in inputs.values():
        pargs += ["--input", str(d)]
    pargs += ["--out", str(plan)]
    if args.confirm_paper:
        pargs.append("--confirm")
        if args.exe:
            pargs += ["--exe", args.exe]
    code, txt = run("sch_page_plan.py", pargs, timeout=7200)
    st.ok = code == 0
    st.detail = tail(txt, 3)
    st.next = "" if st.ok else "有模块连 A1 都装不下 —— 只能拆模块"
    if not st.ok:
        return report(stages, args.json)

    # ── S4b 把规划出的纸型应用回输入 ───────────────────────────────────
    #
    # 不加这一步就会自相矛盾：规划说 M1 要 A1，而输入里还是 A4，
    # 于是 S6 预检必然报"装不下"——预检没错，是输入没跟上规划。
    st = Stage("S4b 应用纸型")
    try:
        plan_doc = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.ok = False
        st.detail = "读不到页面规划：%s" % exc
        st.next = "看 S4 的输出"
        stages.append(st)
        return report(stages, args.json)

    paper_of = {}
    for pg in plan_doc.get("pages") or []:
        chosen = pg.get("confirmedPaper") or pg.get("suggestedPaper")
        if chosen:
            paper_of[pg["module"]] = chosen
    SHEETS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594)}
    applied = {}
    final_inputs = {}
    for page, path in inputs.items():
        doc = json.loads(path.read_text(encoding="utf-8"))
        picks = []
        for mod in (doc.get("connectivity") or {}).get("modules") or []:
            name = paper_of.get(mod.get("id"))
            if name:
                picks.append(name)
        if not picks:
            final_inputs[page] = path
            continue
        # 一页多模块时取**最大**的那张纸
        pick = max(picks, key=lambda n: SHEETS[n][0])
        w, h = SHEETS[pick]
        doc["sheet"] = {"minX": 0, "minY": 0, "maxX": w, "maxY": h}
        # **写到新文件，不改自己的输入。**
        # 就地改写会让上游产物失去证据意义：再跑 fit 预检时看到的纸型已经不是
        # S5 生成的那份，"该装不下"的判据也就无从复现。
        dest = out / ("layout-final-%s.json" % page)
        dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        final_inputs[page] = dest
        applied[page] = pick
    inputs = final_inputs
    st.ok = bool(applied)
    st.detail = "，".join("%s→%s" % (k, v) for k, v in sorted(applied.items())) or \
        "规划里没有可用的纸型"
    st.next = "" if st.ok else "先跑 S4 并给出建议纸型"
    stages.append(st)
    if not st.ok:
        return report(stages, args.json)

    # ── S6 两道预检 ──────────────────────────────────────────────────
    st = Stage("S6 输入预检")
    bad = []
    for page, path in inputs.items():
        c1, t1 = run("sch_module_fit.py", [str(path), "--json"])
        c2, t2 = run("sch_layout_precheck.py", [str(path), "--json"])
        if c1 != 0:
            over = []
            try:
                d1 = json.loads(t1[t1.find("{"):])
                over = [m["module"] for m in d1.get("modules") or [] if not m.get("fits")]
            except (ValueError, KeyError):
                pass
            bad.append("%s 装不下：%s" % (page, ",".join(over) or "见 fit 报告"))
        if c2 != 0:
            probs = []
            try:
                d2 = json.loads(t2[t2.find("{"):])
                probs = (d2.get("problems") or [])[:1]
            except (ValueError, KeyError):
                pass
            bad.append("%s 结构不合法：%s" % (page, probs[0] if probs else "见预检报告"))
    st.ok = not bad
    st.detail = ("%d 页两道预检通过" % len(inputs)) if st.ok else "；".join(bad[:2])
    st.next = "" if st.ok else "按预检逐条修，别直接跑求解器"
    stages.append(st)
    return report(stages, args.json)


def report(stages: list[Stage], as_json: bool) -> int:
    ok = all(s.ok for s in stages if s.ok is not None)
    if as_json:
        print(json.dumps({"ok": ok,
                          "stages": [{"name": s.name, "ok": s.ok,
                                      "detail": s.detail, "next": s.next}
                                     for s in stages]},
                         ensure_ascii=False, indent=2))
    else:
        print("离线链：%s" % ("全部通过 ✅" if ok else "停在中间 ❌"))
        for s in stages:
            mark = "✓" if s.ok else "✗"
            print("  %s %-14s %s" % (mark, s.name, s.detail))
            if s.next:
                print("      下一步：%s" % s.next)
        if ok:
            print()
            print("  下一步：sch lib-layout 逐页出排版稿 → sch compose 落图")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
