"""Markdown renderers for scan, plan, rules and benchmark results."""
from __future__ import annotations


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def render_scan_markdown(result):
    counts = result["counts"]
    lines = [
        "# Skill 知识结构扫描索引",
        "",
        f"- 根目录：`{result['source']['root']}`",
        f"- 基线：`{result['source'].get('git_sha') or 'unknown'}`",
        f"- 工具/目录版本：`{result['tool']['version']}` / "
        f"`{result['catalog_version']}`",
        f"- 文件 {counts['files']}，链接 {counts['links']}，"
        f"必读链接 {counts['required_links']}，错误 {counts.get('errors', 0)}，"
        f"警告 {counts.get('warnings', 0)}",
        "",
        f"> {result['not_proof']}",
        "",
        "## 必读闭包（从 SKILL.md 出发）",
        "",
    ]
    for path in result["graph"]["required_closure"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## 结构提示", ""])
    graph = result["graph"]
    lines.append(f"- 必读链最大深度：{graph['required_depth']}")
    lines.append(f"- 孤立资料：{len(graph['orphans'])}")
    for path in graph["orphans"]:
        lines.append(f"  - `{path}`")
    lines.append(f"- 引用环：{len(graph['cycles'])}")
    for cycle in graph["cycles"]:
        lines.append("  - " + " ↔ ".join(f"`{item}`" for item in cycle))
    lines.append(f"- 重复主题：{len(graph['duplicate_topics'])}")
    for item in graph["duplicate_topics"]:
        lines.append(f"  - {item['kind']} `{item['topic']}`: "
                     + ", ".join(f"`{path}`" for path in item["paths"]))
    lines.extend(["", "## 发现", ""])
    if result["findings"]:
        rows = []
        for item in result["findings"]:
            ignored = "ignored" if item.get("ignored") else ""
            rows.append([
                item["id"], item["severity"], item["check"],
                f"`{item['source']}:{item['line']}`",
                str(item["target"]).replace("|", "\\|"),
                item["detail"].replace("|", "\\|"), ignored,
            ])
        lines.append(_table(
            ["id", "severity", "check", "location", "target", "detail",
             "ignored"], rows))
    else:
        lines.append("未发现失效路径、锚点或越界引用。")
    lines.extend(["", "## 文件与引用索引", ""])
    for record in result["files"]:
        lines.append(f"### `{record['path']}`")
        lines.append("")
        lines.append(f"- 标题：{record['title'] or '（无）'}")
        lines.append(f"- 行/字符/字节：{record['lines']} / {record['chars']} / "
                     f"{record['bytes']}")
        lines.append(f"- SHA-256：`{record['sha256']}`")
        if record["links"]:
            lines.append("")
            for link in record["links"]:
                dest = link["resolved"] or link["target"]
                status = "ok" if link["exists"] else (
                    "external" if link["external"] else "missing")
                anchor = ""
                if link.get("anchor"):
                    anchor = f"#{link['anchor']} " + (
                        "ok" if link.get("anchor_exists") else "missing")
                lines.append(
                    f"- L{link['line']} [{link['role']}] "
                    f"[{link['text'] or 'link'}]({link['target']}) → "
                    f"`{dest}` ({status}) {anchor}".rstrip())
        lines.append("")
    return "\n".join(lines) + "\n"


def render_plan_markdown(result):
    intent = result["intent"]
    lines = [
        "# 任务阅读计划",
        "",
        f"- 任务：`{result['task_type']}`，阶段：`{result['stage']}`，"
        f"EDA：{intent['eda_available']}，自主授权："
        f"{intent['autonomous_authorized']}",
        f"- 范围哈希：`{result['scope_hash']}`",
        f"- 预算：{result['budget']['limit_chars']} 字符，"
        f"必读 {result['budget']['required_chars']}，"
        f"选中 {result['budget']['selected_chars']}，状态 "
        f"`{result['budget']['status']}`",
        "",
        f"> {result['not_proof']}",
        "",
        "## 必读",
        "",
        _table(["文件", "字符", "原因"],
               [[f"`{item['path']}`", item["chars"],
                 "；".join(item["reasons"])] for item in result["required"]]),
        "",
    ]
    for title, key in (("条件读", "conditional"), ("可选", "optional")):
        lines.extend([f"## {title}", ""])
        if result[key]:
            lines.append(_table(["文件", "字符", "原因"],
                                [[f"`{item['path']}`", item["chars"],
                                  "；".join(item["reasons"])]
                                 for item in result[key]]))
        else:
            lines.append("无。")
        lines.append("")
    lines.extend(["## 明确排除", ""])
    if result["excluded"]:
        lines.append(_table(["文件", "原因"], [
            [f"`{item['path']}`",
             "；".join(reason["reason"] for reason in item["reasons"])]
            for item in result["excluded"]]))
    else:
        lines.append("无。")
    lines.extend(["", "## 未确定 / 缺口", ""])
    if result["unknown"]:
        lines.append(_table(["code", "原因"], [
            [f"`{item['code']}`", item["reason"]]
            for item in result["unknown"]]))
    else:
        lines.append("无。")
    lines.extend([
        "",
        "## 执行契约（只是声明，不执行）",
        "",
        f"- actions: {', '.join(result['execution_contract']['actions'])}",
        f"- writes_allowed: {result['execution_contract']['writes_allowed']}",
        f"- eda_required: {result['execution_contract']['eda_required']}",
        f"- approval_gates: "
        f"{', '.join(result['execution_contract']['approval_gates']) or 'none'}",
        "",
    ])
    return "\n".join(lines)


def render_rules_markdown(result):
    lines = [
        "# 规则候选与冲突审查",
        "",
        f"- 规则记录：{result['counts']['rules']}，机器候选："
        f"{result['counts']['machine_candidates']}，"
        f"候选张力：{result['counts']['candidate_tensions']}，"
        f"已审查关系：{result['counts']['reviewed_relations']}，"
        f"确认冲突：{result['counts']['confirmed_conflicts']}",
        f"- 夹具：{result['fixtures']['total']} 对，分类正确 "
        f"{result['fixtures']['correct']} 对",
        "",
        f"> {result['not_proof']}",
        "",
        "## 已审查关系",
        "",
    ]
    for relation in result.get("reviewed_relations", []):
        lines.append(f"### {relation['pair_id']} — {relation['classification']}")
        lines.append("")
        lines.append(f"- 规则：{', '.join(relation['rule_ids'])}")
        lines.append(f"- 重叠条件：{relation['overlap']['condition']}")
        lines.append(f"- 触发场景：{relation['scenario']}")
        lines.append(f"- 例外/处置：{relation['exception']}")
        lines.append(f"- 建议：{relation['resolution']}")
        for evidence in relation.get("evidence", []):
            lines.append(f"- 证据：`{evidence['path']}:{evidence['line']}` — "
                         f"{evidence['quote']}")
        lines.append("")
    lines.extend(["## 夹具分类", ""])
    lines.append(_table(["pair", "expected", "actual", "result"], [
        [item["pair_id"], item["expected"], item["actual"],
         "PASS" if item["ok"] else "FAIL"]
        for item in result["fixtures"]["results"]]))
    lines.extend(["", "## 候选张力（不是确认冲突）", ""])
    for item in result.get("candidates", [])[:30]:
        lines.append(f"- `{item['candidate_id']}` {item['relation']}："
                     f"`{item['rule_a']}` ↔ `{item['rule_b']}`")
    return "\n".join(lines) + "\n"


def render_benchmark_markdown(result):
    scenarios = result["scenarios"]
    metrics = result["metrics"]
    lines = [
        "# 任务阅读计划基准",
        "",
        f"- 场景：{scenarios['total']}（dev {scenarios['dev']}，"
        f"holdout {scenarios['holdout']}），通过 {scenarios['passed']}，"
        f"失败 {scenarios['failed']}",
        f"- 必要约束召回：{metrics['required_recall']}，"
        f"关键遗漏 {metrics['missing_critical_total']}，"
        f"禁止阅读命中 {metrics['forbidden_selected_total']}，"
        f"禁止动作命中 {metrics['forbidden_actions_total']}",
        f"- 无关阅读字节：{metrics['unrelated_bytes_total']}，"
        f"plan 稳定场景：{metrics['stable_scenarios']}",
        "",
        f"> {result['not_proof']}",
        "",
        "## 场景结果",
        "",
        _table(["场景", "split", "结果", "召回", "关键遗漏", "禁止阅读",
                "禁止动作", "缺口码"], [
            [item["scenario"], item["split"],
             "PASS" if item["pass"] else "FAIL",
             item["required_recall"],
             ", ".join(item["missing_critical"]) or "-",
             ", ".join(item["forbidden_selected"]) or "-",
             ", ".join(item["forbidden_actions"]) or "-",
             ", ".join(item["unknown_expected_missing"]) or "-"]
            for item in result["results"]]),
        "",
        "## 限制",
        "",
    ]
    for item in result.get("limitations", []):
        lines.append(f"- {item}")
    if result.get("transforms"):
        lines.extend(["", "## 变形检查", ""])
        lines.append(_table(["变形", "结果", "必读缺失"], [
            [item["transform"], "PASS" if item["ok"] else "FAIL",
             ", ".join(item["required_missing"]) or "-"]
            for item in result["transforms"]["transforms"]]))
    return "\n".join(lines) + "\n"
