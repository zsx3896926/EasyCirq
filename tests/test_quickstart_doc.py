"""按一页纸从零走一遍：它自己必须是对的。

这份测试把 quickstart 里写的每一条命令**照抄跑一遍**。
文档过期或写错，这里就红——不然一页纸会变成"看着对、照着做不通"的东西。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
QUICK = ROOT / "easycirq" / "references" / "enterprise-quickstart.md"


def run(script, args, cwd, env=None):
    """跑 scripts/ 下的脚本（一页纸里还剩少量这种写法）。"""
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(cwd), env=e)


def run_ec(args, cwd, env=None):
    """跑**一页纸里写的**那一层命令：easycirq enterprise ..."""
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run(["easycirq", "enterprise", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(cwd), env=e)


def board(fp="R0603"):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": fp},
         "otherProperties": {},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def test_quickstart_file_exists_and_is_one_page():
    assert QUICK.is_file(), "一页纸不见了"
    lines = QUICK.read_text(encoding="utf-8").splitlines()
    # "一页纸"不该膨胀成第二份完整指南
    assert len(lines) <= 220, f"一页纸已经 {len(lines)} 行，该删了"


def test_step1_and_2_exactly_as_written():
    """照抄第 1、2 步：建库 + 写规则 + 自检。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        lib = work / "knowledge"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [{
                "id": "no-0402", "kind": "hard", "title": "禁用 0402 封装",
                "predicate": {"type": "footprint_forbidden",
                              "patterns": ["0402"]},
                "evidence": "产线贴片下限 0603",
                "verified_on": "在一块 R0402 的板子上跑过，报 fail",
            }]}, ensure_ascii=False), encoding="utf-8")

        proc = run_ec(["audit"], work,
                      env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert proc.returncode == 0, proc.stdout[-800:]
        assert "规则：1 条" in proc.stdout
        assert "全部可加载" in proc.stdout


def test_step4_exactly_as_written():
    """照抄第 4 步：干净板 pass、0402 板 fail，退出码如文档所写。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        lib = work / "knowledge"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [{"id": "no-0402", "kind": "hard", "title": "禁用 0402",
                       "predicate": {"type": "footprint_forbidden",
                                     "patterns": ["0402"]},
                       "evidence": "e", "verified_on": "v"}]},
            ensure_ascii=False), encoding="utf-8")
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib)}

        (work / "clean.json").write_text(json.dumps(board("R0603")),
                                         encoding="utf-8")
        p = run_ec(["check", "--netlist", "clean.json"], work, env)
        assert p.returncode == 0, p.stdout[-600:]
        assert "pass" in p.stdout

        (work / "bad.json").write_text(json.dumps(board("R0402")),
                                       encoding="utf-8")
        p = run_ec(["check", "--netlist", "bad.json"], work, env)
        assert p.returncode == 1, p.stdout[-600:]
        assert "R0402" in p.stdout


def test_step5_exactly_as_written():
    """照抄第 5 步：ledger → promote，输出里两行路径必须一致。"""
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        lib = work / "knowledge"
        lib.mkdir()
        ledger = work / "ledger.json"
        ledger.write_text(json.dumps({
            "schema": "easycirq-review-ledger/v1",
            "entries": [{
                "id": "R-001", "reviewer": "张工", "found": "这颗料停产了",
                "disposition": "rule",
                "rule": {"id": "banned-part", "kind": "hard",
                         "title": "禁用停产器件",
                         "predicate": {"type": "part_forbidden",
                                       "parts": ["S8050"]},
                         "evidence": "供应商 2026-03 停产通知",
                         "verified_on": "在一块用 S8050 的板子上跑过，报 fail"},
            }]}, ensure_ascii=False), encoding="utf-8")

        proc = run_ec(["promote", "--ledger", str(ledger)],
                      work, env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert proc.returncode == 0, proc.stdout[-900:]
        assert "回读确认" in proc.stdout
        # 文档说「两行必须一样」——这里真的验一遍
        wrote = next((l.split("：", 1)[1].strip() for l in proc.stdout.splitlines()
                      if l.startswith("写入目录")), None)
        reads = next((l.split("：", 1)[1].strip() for l in proc.stdout.splitlines()
                      if l.startswith("下次读取")), None)
        assert wrote and reads, proc.stdout[-600:]
        assert wrote == reads, f"写入 {wrote} 与读取 {reads} 不一致"


def test_quickstart_does_not_promise_what_is_not_built():
    """"不能承诺什么"那段必须还在，且不许出现"已接入门禁"之类的话。"""
    text = QUICK.read_text(encoding="utf-8")
    for must in ("没有**接进", "不能**自动", "没有代码读"):
        assert must in text, f"一页纸漏了「不能承诺」的一条：{must}"
