"""企业规范审阅报告：把规则、知识、器件参数合成给人看的一份结论。

两条边界必须钉死：
  · 规则决定 verdict；知识**永远**不影响它
  · 每条结论都能说出出处（哪个文件、命中了什么）
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "easycirq" / "scripts" / "enterprise_review.py"
NL = ROOT / "deliverables" / "fan-controller" / "snapshot" / "list.json"
IT = ROOT / "deliverables" / "fan-controller" / "design" / "intent.json"


def run(args, env=None):
    e = {**os.environ}
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(ROOT), env=e)


def board(fp="R0603"):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": fp}, "otherProperty": {},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def setup_lib(tmp, rules, knowledge=None):
    lib = pathlib.Path(tmp) / "lib"
    lib.mkdir()
    (lib / "rules.json").write_text(json.dumps({
        "schema": "easycirq-enterprise-rules/v1", "rules": rules},
        ensure_ascii=False), encoding="utf-8")
    if knowledge:
        (lib / "kb.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-knowledge/v1",
            "knowledge": knowledge}, ensure_ascii=False), encoding="utf-8")
    return lib


def a_rule():
    return {"id": "no-0402", "kind": "hard", "title": "禁用 0402 封装",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
            "evidence": "产线贴片下限 0603", "verified_on": "跑过"}


def test_clean_board_review_says_clean():
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, [a_rule()])
        nl = pathlib.Path(tmp) / "b.json"
        nl.write_text(json.dumps(board()), encoding="utf-8")
        p = run(["--netlist", str(nl)],
                env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert p.returncode == 0, p.stdout[-800:]
    assert "没有违反已知的企业规范" in p.stdout
    assert "✓ 禁用 0402 封装" in p.stdout


def test_violation_review_cites_clause_owner_and_file():
    """违反时必须给出：违反了哪条、依据哪条规范、找谁、规则来自哪个文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        rule = a_rule()
        rule["owner"] = "硬件部 张工"
        lib = setup_lib(tmp, [rule])
        nl = pathlib.Path(tmp) / "bad.json"
        nl.write_text(json.dumps(board("R0402")), encoding="utf-8")
        p = run(["--netlist", str(nl)],
                env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert p.returncode == 1, p.stdout[-800:]
    assert "违反企业规范" in p.stdout
    assert "R0402" in p.stdout
    assert "产线贴片下限 0603" in p.stdout, "没给出依据"
    assert "硬件部 张工" in p.stdout, "没给出去找谁"
    assert "规则来源" in p.stdout


def test_knowledge_never_changes_the_verdict():
    """知识命中再多也不能把 clean 变成 blocked，反之亦然。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, [a_rule()], knowledge=[{
            "id": "K1", "title": "去耦电容要紧邻电源脚",
            "body": "去耦电容靠电源脚", "tags": ["去耦", "电源"]}])
        nl = pathlib.Path(tmp) / "b.json"
        nl.write_text(json.dumps(board()), encoding="utf-8")
        p = run(["--netlist", str(nl)],
                env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert p.returncode == 0, p.stdout[-800:]
        # 有知识命中，但结论仍是 clean
        assert "没有违反已知的企业规范" in p.stdout
        assert "不影响交付" in p.stdout


def test_empty_library_says_so_instead_of_passing():
    """没有企业库时必须明说，不能显示成「检查通过」。"""
    with tempfile.TemporaryDirectory() as tmp:
        nl = pathlib.Path(tmp) / "b.json"
        nl.write_text(json.dumps(board()), encoding="utf-8")
        p = run(["--netlist", str(nl)],
                env={"EASYCIRQ_KNOWLEDGE_DIR": str(pathlib.Path(tmp) / "none")})
    assert "没有加载到任何企业规则" in p.stdout
    assert "目录不存在" in p.stdout


def test_sibling_files_are_not_reported_as_load_problems():
    """同一个目录放规则+知识+器件是正常用法，不许互相告状。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, [a_rule()], knowledge=[{
            "id": "K1", "title": "去耦", "body": "去耦靠电源脚",
            "tags": ["去耦"]}])
        (lib / "parts.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-parts/v1",
            "parts": {"x": {"value": "X"}}}), encoding="utf-8")
        nl = pathlib.Path(tmp) / "b.json"
        nl.write_text(json.dumps(board()), encoding="utf-8")
        p = run(["--netlist", str(nl)],
                env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert p.returncode == 0, p.stdout[-900:]
    assert "加载问题" not in p.stdout, p.stdout[-900:]


@pytest.mark.skipif(not (NL.is_file() and IT.is_file()), reason="风扇板快照不存在")
def test_real_board_review_cites_a_real_entry():
    """真板 + 仓库示例库：必须引用出具体的知识条目，而不是只说「检索到了」。"""
    p = run(["--netlist", str(NL), "--intent", str(IT),
             "--label", "Fan-Controller-12V",
             "--parts", str(ROOT / "examples" / "enterprise-knowledge"
                           / "parts.company.json")],
            env={"EASYCIRQ_KNOWLEDGE_DIR":
                 str(ROOT / "examples" / "enterprise-knowledge")})
    assert p.returncode == 0, p.stdout[-900:]
    assert "可参考的企业知识" in p.stdout
    assert "命中：" in p.stdout, "召回没说出命中什么"
    assert "来源：" in p.stdout, "召回没说出条目来自哪个文件"
