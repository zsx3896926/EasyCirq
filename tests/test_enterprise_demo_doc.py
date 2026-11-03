"""演示文档里每条命令都必须真能跑。

这份测试把 enterprise-demo.md 里写出来的命令**照抄执行**，
输出里承诺的内容必须出现。文档过期或写错，这里就红。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "enterprise-demo.md"
SCRIPTS = ROOT / "easycirq" / "scripts"

RULE = {
    "schema": "easycirq-enterprise-rules/v1",
    "rules": [{
        "id": "no-0402", "kind": "hard", "title": "禁用 0402 封装",
        "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
        "evidence": "产线贴片下限 0603，0402 需外协",
        "owner": "硬件部 张工",
        "verified_on": "在一块 R0402 的板子上跑过，报 fail",
    }]}


def board(fp="R0603"):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": fp}, "otherProperty": {},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def ec(args, cwd, env=None):
    e = {**os.environ}
    for k in ("EASYCIRQ_KNOWLEDGE_DIR", "EASYCIRQ_ENTERPRISE_HITS"):
        e.pop(k, None)
    if env:
        e.update(env)
    return subprocess.run(["easycirq", "enterprise", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(cwd), env=e)


def test_demo_doc_exists_and_stays_short():
    assert DEMO.is_file(), "演示文档不见了"
    lines = DEMO.read_text(encoding="utf-8").splitlines()
    # 「10 分钟看完」不该长成第二份完整指南
    assert len(lines) <= 230, f"演示已 {len(lines)} 行，该删了"


def test_check_and_review_as_written():
    """场景一：check → fail/exit 1、干净板 pass；review 给出违反+依据+找人。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "rules.company.json").write_text(
            json.dumps(RULE, ensure_ascii=False), encoding="utf-8")
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
               "EASYCIRQ_ENTERPRISE_HITS": str(tmp / "hits.json")}

        bad = tmp / "bad.json"
        bad.write_text(json.dumps(board("R0402")), encoding="utf-8")
        p = ec(["check", "--netlist", str(bad)], tmp, env)
        assert p.returncode == 1, p.stdout[-600:]
        assert "no-0402" in p.stdout and "R0402" in p.stdout

        good = tmp / "good.json"
        good.write_text(json.dumps(board("R0603")), encoding="utf-8")
        p = ec(["check", "--netlist", str(good)], tmp, env)
        assert p.returncode == 0, p.stdout[-600:]

        p = ec(["review", "--netlist", str(bad)], tmp, env)
        assert p.returncode == 1, p.stdout[-600:]
        for must in ("违反企业规范", "依据：", "找谁：", "规则来源"):
            assert must in p.stdout, f"review 缺 {must}：\n{p.stdout[-800:]}"


def test_report_is_self_contained_as_written():
    """场景二：report --out 生成自包含网页，且带那四块 + 问题区。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "rules.company.json").write_text(
            json.dumps(RULE, ensure_ascii=False), encoding="utf-8")
        out = tmp / "kb.html"
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
               "EASYCIRQ_ENTERPRISE_HITS": str(tmp / "hits.json")}
        p = ec(["report", "--out", str(out)], tmp, env)
        assert p.returncode == 0, p.stdout[-600:]
        text = out.read_text(encoding="utf-8")

    for bad in ("http://", "https://", "<script", "@import", "src=", "<link", "cdn"):
        assert bad not in text, f"报告引了外部资源：{bad}"
    for section in ("可执行规则", "可检索知识", "企业器件参数", "读了哪些文件"):
        assert section in text, f"报告缺这一节：{section}"
    assert "本机拦截次数" in text
    assert "不是公司汇总" in text


def test_demo_states_what_is_not_done():
    """「现在还不能做什么」那张表必须在，且不许把未做写成已做。"""
    text = DEMO.read_text(encoding="utf-8")
    assert "现在还不能做什么" in text
    for claim in ("未验证", "未做"):
        assert claim in text
    # 关键：必须明说没在客户 EDA 上验过
    assert "没在客户的 EDA 上验过" in text
    # 必须明说人工编辑仍没有锁（工具写入已加锁）
    assert "人工用编辑器同时改仍未加锁" in text
