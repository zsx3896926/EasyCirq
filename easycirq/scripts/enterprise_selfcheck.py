"""企业知识库自检：查**你自己的库**，不需要任何仓库样例。

和仓库里的 `tools/verify_enterprise.py` 不同——那个用风扇板和自己造的样例跑正反例，
只有开发者能用。这个只读企业目录，回答四个问题：

1. 我的库**被读到了吗**？读的是哪个目录、哪些文件？
2. 有**读不进来**的东西吗？（schema 不对、JSON 坏了、字段非法）
3. 有**永远不会生效**的规则吗？（没有 verified_on、谓词执行不了）
4. 有**永远不会被检索到**的知识吗？（没有可检索文本、标签和内容对不上）

四项里任何一项有问题都返回非零。**"加载了 N 条"不是通过条件。**

用法：

    python enterprise_selfcheck.py
    python enterprise_selfcheck.py --json
    EASYCIRQ_KNOWLEDGE_DIR=/path/to/lib python enterprise_selfcheck.py
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import enterprise_parts  # noqa: E402
import enterprise_rules  # noqa: E402
import knowledge_search  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-dir", help="同时检查某个项目的 .easycirq/knowledge")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    problems = []
    report = {"schema": "easycirq-enterprise-selfcheck/v1"}

    # ── 1) 规则
    rules, rule_src, rule_prob = enterprise_rules.load_rules(
        project_dir=args.project_dir)
    report["rules"] = {
        "count": len(rules),
        "ids": [r["id"] for r in rules],
        "sources": rule_src,
    }
    problems.extend({"where": "规则", **p} for p in rule_prob)
    for rule in rules:
        if not rule.get("verified_on"):
            problems.append({
                "where": "规则", "rule": rule["id"],
                "error": ("缺 verified_on —— 没有证据说明这条规则能触发。"
                          "工具只能确认它被加载，无法证明它有用；"
                          "请写清它曾经抓到过什么")})

    # ── 2) 知识
    known, know_src, know_prob = knowledge_search.collect_knowledge(
        project_dir=args.project_dir)
    report["knowledge"] = {"count": len(known), "ids": [k["id"] for k in known],
                           "sources": know_src}
    problems.extend({"where": "知识", **p} for p in know_prob)
    for dead in knowledge_search.audit(known):
        problems.append({"where": "知识", "id": dead["id"], "error": dead["reason"]})

    # ── 3) 器件
    parts, part_src, part_prob = enterprise_parts.load_parts(
        project_dir=args.project_dir)
    report["parts"] = {"count": len(parts), "keys": sorted(parts),
                       "sources": part_src}
    # 知识目录里同时放规则/知识/器件，schema 不匹配是正常的，不当作错误
    for prob in part_prob:
        if "不是器件库" not in prob.get("error", ""):
            problems.append({"where": "器件", **prob})

    report["problems"] = problems
    report["ok"] = not problems

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("企业知识库自检")
    print()
    for kind in ("rules", "knowledge", "parts"):
        info = report[kind]
        label = {"rules": "规则", "knowledge": "知识", "parts": "器件"}[kind]
        print(f"  {label}：{info['count']} 条")
        for src in info["sources"]:
            note = src.get("note") or f"{len(src['files'])} 个文件"
            print(f"      [{src['layer']}] {src['dir']}  {note}")
    print()

    if problems:
        print(f"发现 {len(problems)} 个问题——**这些不会生效**：")
        for prob in problems:
            where = prob.get("where", "")
            ident = prob.get("rule") or prob.get("id") or ""
            f = prob.get("file") or ""
            print(f"  ✗ [{where}] {f}{' ' + ident if ident else ''}")
            print(f"      {prob['error']}")
        print()
        print("修完再跑一次。库里有东西不等于它生效了。")
        return 1

    if not any(report[k]["count"] for k in ("rules", "knowledge", "parts")):
        print("库里是空的。这不是错误——但你还没开始建。")
        print("先把文件放进下面任一目录，再跑一次：")
        default = pathlib.Path(os.environ.get("EASYCIRQ_KNOWLEDGE_DIR")
                               or pathlib.Path.home() / ".easycirq" / "knowledge")
        print(f"  {default}")
        print(f"  <项目>/.easycirq/knowledge")
        return 0

    print("✓ 全部可加载、无死规则、无死知识。")
    print("  注意：这只能证明「能用」；它到底抓不抓得到问题，要拿一块真板跑一次。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
