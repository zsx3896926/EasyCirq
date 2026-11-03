"""企业知识库浏览与导出：可查、可见、可分发的自包含报告。"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "easycirq" / "scripts" / "enterprise_kb.py"


def run(args, env=None, cwd=None):
    e = {**os.environ}
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180,
                          cwd=str(cwd or ROOT), env=e)


def a_rule(**over):
    r = {"id": "no-0402", "kind": "hard", "title": "禁用 0402 封装",
         "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
         "evidence": "规范 §3.2", "owner": "硬件部 张工",
         "verified_on": "在一块 R0402 的板子上跑过，报 fail"}
    r.update(over)
    return r


def setup_lib(tmp, rules=None, knowledge=None, parts=None):
    lib = pathlib.Path(tmp) / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    if rules is not None:
        (lib / "rules.json").write_text(json.dumps(
            {"schema": "easycirq-enterprise-rules/v1", "rules": rules},
            ensure_ascii=False), encoding="utf-8")
    if knowledge is not None:
        (lib / "kb.json").write_text(json.dumps(
            {"schema": "easycirq-enterprise-knowledge/v1",
             "knowledge": knowledge}, ensure_ascii=False), encoding="utf-8")
    if parts is not None:
        (lib / "parts.json").write_text(json.dumps(
            {"schema": "easycirq-enterprise-parts/v1", "parts": parts},
            ensure_ascii=False), encoding="utf-8")
    return lib


def test_html_is_self_contained():
    """报告要能放到内网共享、双击打开——不许引任何外部资源。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, rules=[a_rule()],
                        knowledge=[{"id": "K1", "title": "去耦",
                                    "body": "去耦靠电源脚", "tags": ["去耦"],
                                    "why_not_rule": "需要 PCB 坐标"}],
                        parts={"p.x": {"value": "X", "measured": {"a": 1}}})
        out = pathlib.Path(tmp) / "kb.html"
        proc = run(["--html-out", str(out)],
                   env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert proc.returncode == 0, proc.stdout[-600:]
        text = out.read_text(encoding="utf-8")

    assert text.startswith("<!DOCTYPE html>")
    assert text.rstrip().endswith("</html>")
    for forbidden in ("http://", "https://", "<script", "@import", "src="):
        assert forbidden not in text, f"报告引了外部资源：{forbidden}"
    for section in ("可执行规则", "可检索知识", "企业器件参数", "读了哪些文件"):
        assert section in text, f"缺这一节：{section}"


def test_rule_without_verified_on_is_flagged_in_the_report():
    """没写 verified_on 的规则要在最上面的问题区里出现，不是只标一格。"""
    with tempfile.TemporaryDirectory() as tmp:
        rule = a_rule()
        rule.pop("verified_on")
        lib = setup_lib(tmp, rules=[rule])
        out = pathlib.Path(tmp) / "kb.html"
        run(["--html-out", str(out)], env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        text = out.read_text(encoding="utf-8")
    assert "不会生效" in text
    assert "没有 verified_on" in text
    assert "未证明会触发" in text


def test_dead_knowledge_is_flagged():
    """永远检索不到的知识条目也要进问题区。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, knowledge=[{"id": "K-DEAD", "title": "",
                                         "body": "", "tags": [],
                                         "why_not_rule": "x"}])
        out = pathlib.Path(tmp) / "kb.html"
        run(["--html-out", str(out)], env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        text = out.read_text(encoding="utf-8")
    assert "K-DEAD" in text
    assert "不会生效" in text


def test_html_escapes_enterprise_content():
    """企业写的内容会进网页——必须转义，否则一条规则标题就能注入脚本。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, rules=[
            a_rule(title='<script>alert("x")</script>',
                   evidence='<img src=x onerror=alert(1)>')])
        out = pathlib.Path(tmp) / "kb.html"
        run(["--html-out", str(out)], env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        text = out.read_text(encoding="utf-8")
    assert "<script>alert" not in text, "标题没转义，能注入脚本"
    assert "&lt;script&gt;" in text, "转义后应看到实体"
    assert "<img src=x" not in text, "依据没转义"


def test_empty_library_says_empty_not_broken():
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "kb.html"
        proc = run(["--html-out", str(out)],
                   env={"EASYCIRQ_KNOWLEDGE_DIR":
                        str(pathlib.Path(tmp) / "nope")})
        assert proc.returncode == 0
        text = out.read_text(encoding="utf-8")
    assert "还是空的" in text
    assert "不会生效" not in text


def test_list_shows_three_kinds():
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, rules=[a_rule()],
                        knowledge=[{"id": "K1", "title": "去耦", "body": "b",
                                    "tags": ["去耦"], "why_not_rule": "需要坐标"}],
                        parts={"p.x": {"value": "X"}})
        proc = run(["--list"], env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert proc.returncode == 0, proc.stdout[-600:]
    assert "可执行规则 1 条" in proc.stdout
    assert "可检索知识 1 条" in proc.stdout
    assert "企业器件参数 1 条" in proc.stdout
    assert "no-0402" in proc.stdout


def test_show_finds_rule_and_part_key():
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, rules=[a_rule()],
                        parts={"mosfet.ao3400a_sot23":
                               {"value": "AO3400A", "measured": {"vgs_th": 1.3}}})
        # 规则按 id
        p1 = run(["--show", "no-0402"],
                 env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert p1.returncode == 0, p1.stdout[-400:]
        assert json.loads(p1.stdout)["title"] == "禁用 0402 封装"
        # 器件按"键"（器件条目没有 id 字段）
        p2 = run(["--show", "mosfet.ao3400a_sot23"],
                 env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        assert p2.returncode == 0, p2.stdout[-400:]
        assert json.loads(p2.stdout)["value"] == "AO3400A"


def test_show_unknown_id_exits_nonzero():
    with tempfile.TemporaryDirectory() as tmp:
        lib = setup_lib(tmp, rules=[a_rule()])
        proc = run(["--show", "nope"], env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert proc.returncode == 2
    assert "找不到" in (proc.stdout + proc.stderr)
