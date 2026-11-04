"""一次审阅：把企业规则、企业知识、企业器件参数合成一份可读的报告。

# 为什么需要

前面几块各自能跑，但没人把它们合起来给**一个人**看。终态第 2 条是
「AI 审阅把企业知识作为上下文检索出来，能指出『这条违反贵司规范』」——
需要一样东西真的把那些话说出来。

# 三条边界

1. **规则能阻断，知识只提示。** 报告里分两栏，不混。规则栏决定 `verdict`，
   知识栏**永不**影响结论——知识伪装成门禁会被误报拖垮。
2. **每条都说出来源。** 规则说来自哪个文件，知识说命中了哪个词，
   器件说这个参数取自哪一层。说不出处的东西人没法判断该不该信。
3. **判不了就说判不了。** 没有企业库、库是空的、检索没命中，都明写，
   不伪装成「检查通过」。
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import enterprise_parts  # noqa: E402
import enterprise_rules  # noqa: E402
import knowledge_search  # noqa: E402


def build(netlist, intent, project_dir=None, parts_override=None):
    rules, rule_src, rule_prob = enterprise_rules.load_rules(
        project_dir=project_dir)
    rule_results, rule_findings = enterprise_rules.evaluate(rules, netlist)

    known, know_src, know_prob = knowledge_search.collect_knowledge(
        project_dir=project_dir)
    tokens, facts = knowledge_search.board_context(netlist, intent)
    hits = knowledge_search.search(known, tokens)

    parts, part_src, part_prob = enterprise_parts.load_parts(
        project_dir=project_dir)
    if parts_override:
        for target in parts_override:
            got, _s, _p = enterprise_parts.load_parts(explicit=target)
            parts.update(got)

    return {
        "rules": {"results": rule_results, "findings": rule_findings,
                  "sources": rule_src, "problems": rule_prob},
        "knowledge": {"hits": hits, "sources": know_src,
                      "problems": know_prob, "context": facts,
                      "total": len(known)},
        "parts": {"count": len(parts), "sources": part_src,
                  "problems": part_prob, "keys": sorted(parts)},
    }


def verdict_of(report):
    hard = [r for r in report["rules"]["results"]
            if r["status"] == "fail" and r["kind"] == "hard"]
    unknown = [r for r in report["rules"]["results"] if r["status"] == "unknown"]
    if hard:
        return "blocked"
    if unknown:
        return "incomplete"
    return "clean"


def render(report, board_label=""):
    lines = []
    v = verdict_of(report)
    head = {"blocked": "❌ 违反企业规范，不能交付",
            "incomplete": "⚠️ 有规则判不了，结论不完整",
            "clean": "✅ 没有违反已知的企业规范"}[v]
    lines.append(f"企业规范审阅：{head}")
    if board_label:
        lines.append(f"  板子：{board_label}")
    lines.append("")

    # ── 规则栏
    results = report["rules"]["results"]
    lines.append(f"一、可执行规则（{len(results)} 条，**影响交付**）")
    if not results:
        lines.append("  （没有加载到任何企业规则）")
        for src in report["rules"]["sources"]:
            note = src.get("note") or f"{len(src['files'])} 个文件"
            lines.append(f"      [{src['layer']}] {src['dir']}  {note}")
    for r in results:
        mark = {"pass": "✓", "fail": "✗", "unknown": "?"}[r["status"]]
        kind = f"[{r['kind']}]" if r["status"] == "fail" else ""
        lines.append(f"  {mark} {r.get('title') or r['id']} {kind}".rstrip())
        if r["status"] == "fail":
            for vline in r.get("violations") or []:
                lines.append(f"      违反：{vline}")
            if r.get("evidence"):
                lines.append(f"      依据：{r['evidence']}")
            if r.get("owner"):
                lines.append(f"      找谁：{r['owner']}")
            lines.append(f"      规则来源：{r.get('file')}")
    lines.append("")

    # ── 知识栏
    k = report["knowledge"]
    lines.append(f"二、可参考的企业知识（{len(k['hits'])}/{k['total']} 条命中，"
                 f"**不影响交付**）")
    for h in k["hits"]:
        lines.append(f"  · {h['title']}")
        lines.append(f"      命中：{'；'.join(h['matched_on'])}")
        lines.append(f"      来源：{h['from']}")
    if not k["hits"]:
        lines.append("  （这块板没有命中任何企业知识——不代表没问题，"
                     "只是库里没有相关的）")
    if k["context"]:
        lines.append("  上下文：" + "；".join(k["context"])[:160])
    lines.append("")

    # ── 判不了 / 加载问题
    problems = (report["rules"]["problems"] + report["knowledge"]["problems"]
                + report["parts"]["problems"])
    if problems:
        lines.append(f"三、加载问题（{len(problems)} 处，**这些条目不会生效**）")
        for p in problems:
            lines.append(f"  ! {p.get('file')}: {p['error']}")
        lines.append("")

    lines.append("──")
    lines.append("规则决定能不能交付；知识只是提醒，从不算通过或失败。")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--intent")
    ap.add_argument("--project-dir")
    ap.add_argument("--parts", action="append", default=[])
    ap.add_argument("--label", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    netlist = json.loads(pathlib.Path(args.netlist).read_text(encoding="utf-8-sig"))
    netlist = netlist.get("result") or netlist
    intent = None
    if args.intent:
        intent = json.loads(pathlib.Path(args.intent).read_text(encoding="utf-8-sig"))
        intent = intent.get("result") or intent

    report = build(netlist, intent, args.project_dir, args.parts or None)
    v = verdict_of(report)

    if args.json:
        print(json.dumps({"schema": "easycirq-enterprise-review/v1",
                          "verdict": v, **report},
                         ensure_ascii=False, indent=2))
    else:
        print(render(report, args.label))

    return 1 if v == "blocked" else (2 if v == "incomplete" else 0)


if __name__ == "__main__":
    sys.exit(main())
