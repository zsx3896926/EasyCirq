"""人审记录 → 企业规则 → 下次自动生效。

这个模块的核心承诺是**闭环**：人指出一个问题，标记为规则，推进去，
下一次画板时它真的会拦住。所以测试全部按"故意违反 → 必须被拦"来写，
而不是"记录保存成功"。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER_TOOL = ROOT / "easycirq" / "scripts" / "review_ledger.py"
RULES_TOOL = ROOT / "easycirq" / "scripts" / "enterprise_rules.py"
EXAMPLE = ROOT / "examples" / "enterprise-knowledge" / "review-ledger.example.json"


def run(tool, args, env=None):
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(tool), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, cwd=str(ROOT), env=e)


def board(footprint="R0603"):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": footprint},
         "otherProperty": {"Manufacturer Part": "X"},
         "pins": [{"pinNumber": "1", "net": "A"}, {"pinNumber": "2", "net": "B"}]},
    ]}


def write_ledger(dirpath, entries):
    p = pathlib.Path(dirpath) / "ledger.json"
    p.write_text(json.dumps({"schema": "easycirq-review-ledger/v1",
                             "entries": entries}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def good_rule_entry(rid="R-1", **rule_over):
    rule = {"id": "no-0402", "kind": "hard", "title": "禁用 0402",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
            "evidence": "规范 §3.2",
            "verified_on": "用一块 R0402 的板跑过，报 fail"}
    rule.update(rule_over)
    return {"id": rid, "date": "2026-11-02", "reviewer": "张工",
            "found": "产线贴不了 0402", "disposition": "rule", "rule": rule}


def test_example_ledger_is_valid():
    proc = run(LEDGER_TOOL, ["--ledger", str(EXAMPLE), "--verify"])
    assert proc.returncode == 0, proc.stdout[-800:]


def test_missing_disposition_is_rejected():
    """不选边就是不合格 —— 工具不替人判断规则还是知识。"""
    with tempfile.TemporaryDirectory() as tmp:
        entry = good_rule_entry()
        entry.pop("disposition")
        ledger = write_ledger(tmp, [entry])
        proc = run(LEDGER_TOOL, ["--ledger", str(ledger), "--verify"])
        assert proc.returncode == 2
        assert "必须显式选边" in proc.stdout


def test_rule_with_unexecutable_predicate_is_rejected():
    """标了 rule 但谓词执行不了 → 当场拒绝，不许"存进去看起来生效"。"""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = write_ledger(tmp, [good_rule_entry(
            predicate={"type": "no_such_predicate"})])
        proc = run(LEDGER_TOOL, ["--ledger", str(ledger), "--verify"])
        assert proc.returncode == 2
        assert "不可执行" in proc.stdout


def test_rule_without_verified_on_is_rejected():
    """能把规则加载 ≠ 规则有用。缺 verified_on 就是"存了但没生效"。"""
    with tempfile.TemporaryDirectory() as tmp:
        entry = good_rule_entry()
        entry["rule"].pop("verified_on")
        ledger = write_ledger(tmp, [entry])
        proc = run(LEDGER_TOOL, ["--ledger", str(ledger), "--verify"])
        assert proc.returncode == 2
        assert "verified_on" in proc.stdout


def test_knowledge_entry_needs_title_and_body():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = write_ledger(tmp, [{
            "id": "K-1", "reviewer": "李工", "found": "某经验",
            "disposition": "knowledge", "knowledge": {"title": "只有标题"},
        }])
        proc = run(LEDGER_TOOL, ["--ledger", str(ledger), "--verify"])
        assert proc.returncode == 2
        assert "body" in proc.stdout


def test_promote_then_rule_blocks_a_bad_board():
    """完整闭环：推进 → 回读确认加载 → 不加任何参数，违规板必须被拦住。"""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = write_ledger(tmp, [good_rule_entry()])
        target = pathlib.Path(tmp) / "knowledge"

        proc = run(LEDGER_TOOL, ["--ledger", str(ledger),
                                 "--promote", "--target", str(target)])
        assert proc.returncode == 0, proc.stdout[-800:]
        assert "回读确认" in proc.stdout

        nl = pathlib.Path(tmp) / "bad.json"
        nl.write_text(json.dumps(board("R0402"), ensure_ascii=False),
                      encoding="utf-8")
        check = run(RULES_TOOL, ["--netlist", str(nl)],
                    env={"EASYCIRQ_KNOWLEDGE_DIR": str(target)})
        assert check.returncode == 1, check.stdout[-800:]
        assert "no-0402" in check.stdout


def test_promoted_rule_lets_a_clean_board_through():
    """闭环的另一半：规则生效了，但干净板不能被误伤。"""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = write_ledger(tmp, [good_rule_entry()])
        target = pathlib.Path(tmp) / "knowledge"
        run(LEDGER_TOOL, ["--ledger", str(ledger),
                          "--promote", "--target", str(target)])
        nl = pathlib.Path(tmp) / "good.json"
        nl.write_text(json.dumps(board("R0603"), ensure_ascii=False),
                      encoding="utf-8")
        check = run(RULES_TOOL, ["--netlist", str(nl)],
                    env={"EASYCIRQ_KNOWLEDGE_DIR": str(target)})
        assert check.returncode == 0, check.stdout[-800:]


def test_knowledge_only_ledger_promotes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = write_ledger(tmp, [{
            "id": "K-1", "reviewer": "李工", "found": "经验",
            "disposition": "knowledge",
            "knowledge": {"title": "t", "body": "b"},
        }])
        proc = run(LEDGER_TOOL, ["--ledger", str(ledger),
                                 "--promote", "--target",
                                 str(pathlib.Path(tmp) / "knowledge")])
        assert proc.returncode == 0
        assert "无需写入" in proc.stdout


def test_promote_defaults_to_the_env_dir_not_home():
    """设了 EASYCIRQ_KNOWLEDGE_DIR 时，promote 不给 --target 必须写到那里。

    这是 2026-11-03 实测出来的真实缺陷：默认写死 ~/.easycirq/knowledge，
    而读取规则看的是环境变量目录，于是规则「存了但不生效」——而且 promote
    还报成功，因为它的回读把环境变量临时改成了写入目标，验的是自己刚设的路径。
    工具主动把「存了」说成「生效了」，是这个目标明令禁止的最恶劣一类。
    """
    with tempfile.TemporaryDirectory() as tmp:
        company = pathlib.Path(tmp) / "company-lib"
        company.mkdir()
        ledger = write_ledger(tmp, [good_rule_entry()])

        proc = run(LEDGER_TOOL, ["--ledger", str(ledger), "--promote"],
                   env={"EASYCIRQ_KNOWLEDGE_DIR": str(company)})
        assert proc.returncode == 0, proc.stdout[-800:]
        assert (company / "rules.from-review.json").is_file(), \
            "规则没写进环境变量指定的目录"
        # 输出要让人一眼看见「写哪」和「下次读哪」
        assert "写入目录" in proc.stdout and "下次读取" in proc.stdout

        # 关键：下一次真实运行必须能找到并拦住
        nl = pathlib.Path(tmp) / "bad.json"
        nl.write_text(json.dumps(board("R0402"), ensure_ascii=False),
                      encoding="utf-8")
        check = run(RULES_TOOL, ["--netlist", str(nl)],
                    env={"EASYCIRQ_KNOWLEDGE_DIR": str(company)})
        assert check.returncode == 1, (
            "规则推进入了却拦不住板子：\n" + check.stdout[-800:])
