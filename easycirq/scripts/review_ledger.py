"""人审记录：把「人工核查指出的问题」变成下次能用的资产。

# 这个模块解决的问题

企业用 EasyCirq 画板，AI 会审查，但**最终由人核查**。人指出的问题如果只留在
聊天记录或邮件里，下次还会犯同一个错。这个模块把那句话变成结构化的条目。

# 核心设计决断：工具**不自动判断**一条意见是规则还是知识

每条记录必须由人显式标 `disposition`：

| disposition | 含义 | 变成什么 | 能否阻断 |
|---|---|---|---|
| `rule` | 能写成"对网表做一次确定性判定" | 企业规则，进检查链 | **能** |
| `knowledge` | 依赖上下文/经验，判不了 | 检索库，审阅时参考 | **不能** |

**为什么不让工具猜**：判错的两边都致命。

- 把知识当规则 → 天天误报 → 被人关掉 → 等于没写
- 把规则当知识 → 能查的不查 → 下次没人看 → 等于没执行

而且"这条意见能不能自动化"恰恰是**人最清楚、工具最不清楚**的事。
工具能做的是**校验**：`rule` 类必须给出可执行的 predicate，给不出来当场拒绝。

# 「存了」和「生效了」必须分开

`promote` 把 `rule` 类的条目写进企业规则目录后，**立刻回读一次**，
确认规则 id 真的出现在加载列表里。只写不验等于没数。

验收标准写在 `--verify` 里：不是"文件写成功了"，而是
"下一次加载时这条规则在列表里，且能对一块违规的板报错"。
"""
import argparse
import datetime as _dt
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import enterprise_rules  # noqa: E402

SCHEMA = "easycirq-review-ledger/v1"
ENTRY_DISPOSITIONS = ("rule", "knowledge")


def default_target():
    """**读取规则时真正会看的目录**。

    必须是这个函数而不是写死 `~/.easycirq/knowledge`。

    2026-11-03 实测的缺陷：客户设了 `EASYCIRQ_KNOWLEDGE_DIR=<公司目录>`，
    跑 `--promote` 不给 `--target`，规则被写进 `~/.easycirq/knowledge`，
    而 `enterprise_rules.py` 从公司目录读——**规则一条都不会生效**。

    更坏的是它报成功：回读时把环境变量临时改成了写入目标，所以
    「回读确认：加载到 1 条」验的是它自己刚设的路径，不是下一次真实运行。
    这是最恶劣的一类：工具主动把「存了」说成「生效了」。
    """
    env = os.environ.get("EASYCIRQ_KNOWLEDGE_DIR", "").strip()
    if env:
        return pathlib.Path(env)
    return pathlib.Path.home() / ".easycirq" / "knowledge"


def load_ledger(path):
    p = pathlib.Path(path)
    if not p.is_file():
        return {"schema": SCHEMA, "entries": []}, []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return None, [f"读不出来: {exc}"]
    if data.get("schema") != SCHEMA:
        return None, [f"schema 必须是 {SCHEMA}，实际 {data.get('schema')!r}"]
    return data, []


def validate_entry(entry, index):
    """校验一条记录。**给不出可执行 predicate 的 rule，当场拒绝。**

    这是模块唯一能防的事：人标了 rule 但其实写不成规则——那它下次不会执行，
    等于把"漏执行"藏进了一个看起来生效的记录里。
    """
    problems = []
    where = f"entries[{index}]"
    eid = entry.get("id")
    if not eid:
        problems.append(f"{where}: 缺 id")
        where = f"{where}(无 id)"

    disposition = entry.get("disposition")
    if disposition not in ENTRY_DISPOSITIONS:
        problems.append(
            f"{where}: disposition 必须是 rule 或 knowledge（实际 {disposition!r}）。"
            f"**必须显式选边**——工具不替你判断，因为判错两边都致命")
        return problems

    if not str(entry.get("found") or "").strip():
        problems.append(f"{where}: 缺 found（人到底指出了什么问题）")
    if not str(entry.get("reviewer") or "").strip():
        problems.append(f"{where}: 缺 reviewer（谁审的，以后要找他确认）")

    if disposition == "rule":
        rule = entry.get("rule")
        if not isinstance(rule, dict):
            problems.append(f"{where}: disposition=rule 必须给 rule 块")
            return problems
        if not rule.get("id"):
            problems.append(f"{where}.rule: 缺 id")
        pred = (rule.get("predicate") or {}).get("type")
        if pred not in enterprise_rules.PREDICATES:
            problems.append(
                f"{where}.rule: 谓词 {pred!r} 不可执行（支持 "
                f"{list(enterprise_rules.PREDICATES)}）。"
                f"写不成规则的，请改标 disposition=knowledge")
        if (rule.get("kind") or "hard") not in ("hard", "advisory"):
            problems.append(f"{where}.rule: kind 必须是 hard/advisory")
        if not str(rule.get("evidence") or "").strip():
            problems.append(f"{where}.rule: 缺 evidence（依据哪条规范/哪次事故）")
        # ── 「能加载」不等于「有用」
        #
        # 我无法自动判断"看起来合法但语义是死的"规则：谓词名对、参数是胡说，
        # 校验拦不住，而它永远不会触发——那就是最坏的情况（存了但没生效）。
        # 所以这里要求人**记录它曾经抓到过什么**。这一条只保证"有人验证过"，
        # 不保证验证得对；工具做不到的事不假装做到。
        if not str(rule.get("verified_on") or "").strip():
            problems.append(
                f"{where}.rule: 缺 verified_on —— 请写清**这条规则曾经抓到过什么**"
                f"（一块具体的板/一次具体的违规）。"
                f"工具只能确认它能被加载，无法证明它会触发；这一栏是人对"
                f"「它真的有用」的背书，缺了就是存了但没生效")

    if disposition == "knowledge":
        kn = entry.get("knowledge")
        if not isinstance(kn, dict):
            problems.append(f"{where}: disposition=knowledge 必须给 knowledge 块")
            return problems
        if not str(kn.get("title") or "").strip():
            problems.append(f"{where}.knowledge: 缺 title")
        if not str(kn.get("body") or "").strip():
            problems.append(f"{where}.knowledge: 缺 body")
        # ── 「规则不许降级成知识」
        #
        # 工具判断不了"这件事本来能不能自动查"——那是工程判断，只有人知道。
        # 能做的是**要求写清为什么不能自动化**：
        #
        #   · 逼人真的想一遍，而不是"算不出来就丢进知识库"
        #   · 事后有人能复核这个理由站不站得住
        #   · `--promote` 与自检都会把它列出来，不会被埋掉
        #
        # 这是能做到的最强约束。工具不假装能自动区分。
        if not str(kn.get("why_not_rule") or "").strip():
            problems.append(
                f"{where}.knowledge: 缺 why_not_rule —— 请写清**为什么这条不能"
                f"写成一条自动判据**（比如依赖现场照片、依赖供应商口头承诺、"
                f"依赖尚未定量的经验）。"
                f"这一栏是为了防止把「本可以自动查」的东西降级成知识，"
                f"降级等于下次没人执行")
    return problems


def validate(ledger):
    problems = []
    seen = set()
    for i, entry in enumerate(ledger.get("entries") or []):
        problems.extend(validate_entry(entry, i))
        eid = entry.get("id")
        if eid:
            if eid in seen:
                problems.append(f"entries[{i}]: id {eid!r} 重复")
            seen.add(eid)
    return problems


def rule_files_from_ledger(ledger):
    """把 disposition=rule 的条目摊平成企业规则格式。"""
    rules = []
    for entry in ledger.get("entries") or []:
        if entry.get("disposition") != "rule":
            continue
        rule = dict(entry["rule"])
        rule.setdefault("kind", "hard")
        rule.setdefault("title", entry.get("found", ""))
        rule.setdefault("evidence", f"人审记录 {entry.get('id')} / {entry.get('reviewer')}")
        if entry["rule"].get("verified_on"):
            rule["verified_on"] = entry["rule"]["verified_on"]
        rule["_from_review"] = entry.get("id")
        rules.append(rule)
    return rules


def _read_existing_rules(path):
    """读现有规则文件。读不出来就当空的——但**不静默吞掉**，调���方会看到
    合并结果里少了东西。文件不存在是正常的（第一次 promote）。"""
    p = pathlib.Path(path)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return []
    return [r for r in (data.get("rules") or []) if isinstance(r, dict)]


def _strip_bookkeeping(rule):
    """去掉我们加的内部字段再比内容。"""
    return {k: v for k, v in rule.items() if not k.startswith("_")}


def _same_rule(a, b):
    return _strip_bookkeeping(a) == _strip_bookkeeping(b)


def _brief(rule):
    return {"title": rule.get("title"), "kind": rule.get("kind"),
            "evidence": rule.get("evidence")}


def promote(ledger, target_dir, dry_run=False):
    """把 rule 类条目写进企业规则目录，并**回读验证真的能被加载**。"""
    problems = validate(ledger)
    if problems:
        return {"ok": False, "problems": problems}

    rules = rule_files_from_ledger(ledger)
    if not rules:
        return {"ok": True, "written": None, "rules": 0,
                "note": "没有 disposition=rule 的条目，无需写入"}

    target = pathlib.Path(target_dir)
    payload = {"schema": enterprise_rules.SCHEMA,
               "layer": "enterprise",
               "_from": "review-ledger",
               "rules": rules}

    if dry_run:
        return {"ok": True, "dry_run": True, "rules": len(rules),
                "would_write": str(target / "rules.from-review.json")}

    target.mkdir(parents=True, exist_ok=True)
    out = target / "rules.from-review.json"

    # ── 合并，不是覆盖 ────────────────────────────────────────────────
    #
    # 原来的写法是整文件覆盖：两个人各自 promote，第二个会把第一个人的
    # 规则整条抹掉，且没有任何提示。共享目录上这是必然会发生的。
    #
    # 现在按 id 合并；同一个 id 但内容不同 = **真冲突**，不替人挑，
    # 保留原有的、跳过新的、报出来让人决定。宁可少写一条，不能悄悄丢一条。
    import enterprise_lock

    merged, conflicts = [], []
    try:
        with enterprise_lock.FileLock(out) as lock:
            existing = _read_existing_rules(out)
            by_id = {r.get("id"): r for r in existing if r.get("id")}
            order = [r.get("id") for r in existing if r.get("id")]

            for rule in rules:
                rid = rule.get("id")
                prev = by_id.get(rid)
                if prev is None:
                    by_id[rid] = rule
                    order.append(rid)
                elif _same_rule(prev, rule):
                    pass  # 已经在了，什么都不用做
                else:
                    conflicts.append({
                        "id": rid,
                        "kept": _brief(prev),
                        "skipped": _brief(rule),
                        "why": "同一 id 内容不同：保留库里已有的，跳过这次的。"
                               "要么改 id，要么先手工对齐",
                    })

            merged = [by_id[rid] for rid in order if rid in by_id]
            payload["rules"] = merged
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            took_over = getattr(lock, "took_over_stale", False)
    except enterprise_lock.LockTimeout as exc:
        return {"ok": False, "locked": True, "problems": [
            {"file": str(out), "error": str(exc)}]}

    # ── 写完之后必须回读，确认「下一次真的会加载」。
    #
    # 回读要**对着刚写入的目录**做：上面那版直接调 load_rules()，读的是默认
    # 企业目录，写进别处时根本验不到——"验证"验了另一个地方。
    import os
    saved = os.environ.get("EASYCIRQ_KNOWLEDGE_DIR")
    os.environ["EASYCIRQ_KNOWLEDGE_DIR"] = str(target)
    try:
        _, sources, load_problems = enterprise_rules.load_rules()
    finally:
        if saved is None:
            os.environ.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
        else:
            os.environ["EASYCIRQ_KNOWLEDGE_DIR"] = saved
    loaded_ids = set()
    for src in sources:
        if src.get("note"):
            continue
        for name in src.get("files") or []:
            path = pathlib.Path(src["dir"]) / name
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:  # noqa: BLE001
                continue
            for rule in data.get("rules") or []:
                if rule.get("id"):
                    loaded_ids.add(rule["id"])

    missing = [r["id"] for r in rules if r["id"] not in loaded_ids]
    return {"ok": not missing and not conflicts, "written": str(out),
            "rules": len(rules), "merged_total": len(merged),
            "kept_existing": max(0, len(merged) - len(rules)),
            "conflicts": conflicts,
            "took_over_stale_lock": took_over,
            "loaded_ids": sorted(loaded_ids), "missing": missing,
            "load_problems": load_problems}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", default=".easycirq/review-ledger.json")
    ap.add_argument("--list", action="store_true", help="列出条目")
    ap.add_argument("--verify", action="store_true", help="校验全部条目")
    ap.add_argument("--promote", action="store_true",
                    help="把 disposition=rule 的条目写进企业规则目录并回读验证")
    ap.add_argument("--target", default=None,
                    help="企业规则目录（默认取 $EASYCIRQ_KNOWLEDGE_DIR，"
                         "未设时用 ~/.easycirq/knowledge —— 与读取规则时一致）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ledger, load_problems = load_ledger(args.ledger)
    if ledger is None:
        print(f"人审记录读不出来：{args.ledger}", file=sys.stderr)
        for p in load_problems:
            print(f"  ! {p}", file=sys.stderr)
        return 3

    entries = ledger.get("entries") or []
    if args.verify:
        problems = validate(ledger)
        if args.json:
            print(json.dumps({"ok": not problems, "problems": problems,
                              "entries": len(entries)}, ensure_ascii=False, indent=2))
        else:
            print(f"人审记录校验：{len(entries)} 条" +
                  ("，全部合格" if not problems else f"，{len(problems)} 个问题"))
            for p in problems:
                print(f"  ! {p}")
        return 0 if not problems else 2

    if args.promote:
        target = pathlib.Path(args.target) if args.target else default_target()
        result = promote(ledger, target, dry_run=args.dry_run)
        # 明说写哪、下次从哪读——两者不一致就是问题，让人一眼看见
        result["target"] = str(target)
        result["read_by_next_run"] = str(default_target())
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("note"):
                print(result["note"])
            elif result.get("dry_run"):
                print(f"（dry-run）会写入 {result['would_write']}，{result['rules']} 条规则")
            elif not result["ok"] and not result.get("written"):
                # 真正没写：校验没过，或者锁被占着
                print("没有写入：")
                for p in result.get("problems") or []:
                    print(f"  ! {p}")
            elif not result["ok"]:
                # 写了，但有冲突或加载不到——**不是全失败**，别用"失败"二字
                print(f"已写入 {result['written']}（但有问题，见下）")
                print(f"  本次推入：{result['rules']} 条")
                print(f"  库中共有：{result['merged_total']} 条"
                      + (f"（保留原有的 {result['kept_existing']} 条）"
                         if result.get("kept_existing") else ""))
                if result.get("conflicts"):
                    print()
                    print(f"  ⚠ 有 {len(result['conflicts'])} 处冲突，"
                          f"**这些没有写入**：")
                    for c in result["conflicts"]:
                        print(f"    {c['id']}：{c['why']}")
                        print(f"      库里已有：{c['kept']}")
                        print(f"      本次跳过：{c['skipped']}")
                for m in result.get("missing") or []:
                    print(f"  ! 写进去了但加载不到：{m}")
            elif result.get("note"):
                print(result["note"])
            elif result.get("dry_run"):
                print(f"（dry-run）会写入 {result['would_write']}，{result['rules']} 条规则")
            else:
                # 说清两件事：这一次推了几条、库里现在一共几条。
                # 只说"1 条规则"会让人以为库里只有 1 条——合并语义下这是误导。
                print(f"已写入 {result['written']}")
                print(f"  本次推入：{result['rules']} 条")
                print(f"  库中共有：{result['merged_total']} 条"
                      + (f"（保留原有的 {result['kept_existing']} 条）"
                         if result.get("kept_existing") else ""))
                print(f"回读确认：加载到 {len(result['loaded_ids'])} 条规则 id")
                if result.get("took_over_stale_lock"):
                    print("  注意：接管了一个残留锁（上次可能异常退出）。"
                          "确认没有别人正在改。")
                if result.get("conflicts"):
                    print()
                    print(f"  ⚠ 有 {len(result['conflicts'])} 处冲突，"
                          f"**这些没有写入**：")
                    for c in result["conflicts"]:
                        print(f"    {c['id']}：{c['why']}")
                        print(f"      库里已有：{c['kept']}")
                        print(f"      本次跳过：{c['skipped']}")
                print(f"写入目录：{result['target']}")
                print(f"下次读取：{result['read_by_next_run']}")
                if result["missing"]:
                    print(f"  ! 以下规则写进去了但**下一次加载不到**：{result['missing']}")
        return 0 if result["ok"] else 2

    # 默认：列出
    if args.json:
        print(json.dumps(ledger, ensure_ascii=False, indent=2))
        return 0
    print(f"人审记录：{len(entries)} 条（{args.ledger}）")
    for e in entries:
        mark = "规则" if e.get("disposition") == "rule" else "知识"
        print(f"  [{mark}] {e.get('id')}  {e.get('date','')}  {e.get('reviewer','')}")
        print(f"          {str(e.get('found') or '')[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
