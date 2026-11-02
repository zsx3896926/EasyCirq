"""客户自检：面向**企业自己的库**，不是仓库样例。

这个工具的承诺是"库里的东西真的会生效"。所以测试盯的是它能不能
把「不会生效」的东西抓出来，而不是"能跑通"。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "easycirq" / "scripts" / "enterprise_selfcheck.py"


def run(args=None, env=None):
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(TOOL), *(args or [])],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(ROOT), env=e)


def write_rules(dirpath, rules):
    (pathlib.Path(dirpath) / "rules.json").write_text(
        json.dumps({"schema": "easycirq-enterprise-rules/v1", "rules": rules},
                   ensure_ascii=False), encoding="utf-8")


def good_rule(**over):
    rule = {"id": "no-0402", "kind": "hard", "title": "禁用 0402",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
            "evidence": "规范 §3.2",
            "verified_on": "用一块 R0402 的板跑过，报 fail"}
    rule.update(over)
    return rule


def test_empty_library_is_not_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run(env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 0
        assert "库里是空的" in proc.stdout


def test_clean_library_passes():
    with tempfile.TemporaryDirectory() as tmp:
        write_rules(tmp, [good_rule()])
        proc = run(env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 0, proc.stdout[-800:]
        assert "全部可加载" in proc.stdout


def test_rule_without_verified_on_is_flagged():
    """没被证明会触发的规则 = 存了但没生效，必须抓出来。"""
    with tempfile.TemporaryDirectory() as tmp:
        rule = good_rule()
        rule.pop("verified_on")
        write_rules(tmp, [rule])
        proc = run(env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 1, proc.stdout[-800:]
        assert "verified_on" in proc.stdout
        assert "no-0402" in proc.stdout


def test_unexecutable_predicate_is_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        write_rules(tmp, [good_rule(predicate={"type": "made_up"})])
        proc = run(env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 1
        assert "made_up" in proc.stdout


def test_sibling_schemas_are_not_reported_as_problems():
    """同一个目录放规则+知识+器件是正常用法，不许互相告状。"""
    with tempfile.TemporaryDirectory() as tmp:
        write_rules(tmp, [good_rule()])
        (pathlib.Path(tmp) / "parts.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-parts/v1",
            "parts": {"x": {"value": "X"}}}), encoding="utf-8")
        (pathlib.Path(tmp) / "kb.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-knowledge/v1",
            "knowledge": [{"id": "K1", "title": "去耦电容紧邻电源脚",
                           "body": "去耦电容要靠近 ic 电源脚", "tags": ["去耦"]}]}),
            encoding="utf-8")
        proc = run(env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 0, proc.stdout[-1000:]
        assert "全部可加载" in proc.stdout


def test_dead_knowledge_is_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / "kb.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-knowledge/v1",
            "knowledge": [{"id": "K-DEAD", "title": "", "body": "", "tags": []}]}),
            encoding="utf-8")
        proc = run(env={"EASYCIRQ_KNOWLEDGE_DIR": tmp})
        assert proc.returncode == 1
        assert "K-DEAD" in proc.stdout
