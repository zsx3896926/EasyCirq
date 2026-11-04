"""拦截计数：把「拦过什么」从人的声明变成运行记录。

两条边界必须守住：
  · 计数是**本机**记录，报告里必须标出来，不许当成公司汇总
  · 写不进去（只读盘/共享冲突）不许让检查失败——它只是附加信息
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
sys.path.insert(0, str(SCRIPTS))

import enterprise_rules  # noqa: E402


def a_rule(rid="no-0402", kind="hard"):
    return {"id": rid, "kind": kind, "title": "禁用 0402",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
            "evidence": "e", "owner": "硬件部", "verified_on": "v"}


def board(fp="R0402"):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": fp}, "otherProperty": {},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def test_record_hits_counts_only_violations():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "hits.json"
        results = [
            {"id": "r-fail", "status": "fail", "kind": "hard"},
            {"id": "r-pass", "status": "pass", "kind": "hard"},
            {"id": "r-unknown", "status": "unknown", "kind": "hard"},
        ]
        hits = enterprise_rules.record_hits(results, p)
        assert hits["r-fail"]["count"] == 1
        assert "r-pass" not in hits, "通过的规则不该计数"
        assert "r-unknown" not in hits, "判不了的规则不该计数"


def test_record_hits_accumulates():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "hits.json"
        results = [{"id": "r1", "status": "fail", "kind": "hard"}]
        enterprise_rules.record_hits(results, p)
        enterprise_rules.record_hits(results, p)
        hits = enterprise_rules.record_hits(results, p)
        assert hits["r1"]["count"] == 3
        assert hits["r1"]["last_seen"], "应当记录最后一次时间"


def test_hits_survive_a_corrupt_file():
    """计数文件坏了不该让检查失败——它只是附加信息。"""
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "hits.json"
        p.write_text("{ 这不是 json", encoding="utf-8")
        assert enterprise_rules.load_hits(p) == {}
        hits = enterprise_rules.record_hits(
            [{"id": "r1", "status": "fail", "kind": "hard"}], p)
        assert hits["r1"]["count"] == 1, "坏了应当重来，不是崩掉"


def test_unwritable_hits_path_does_not_break_the_check():
    with tempfile.TemporaryDirectory() as tmp:
        # 指向一个不存在且不可创建的父路径下的文件
        p = pathlib.Path(tmp) / "no" / "such" / "deep" / "hits.json"
        hits = enterprise_rules.record_hits(
            [{"id": "r1", "status": "fail", "kind": "hard"}], p)
        # 内存里的结果还在，只是没落盘
        assert hits["r1"]["count"] == 1


def run(script, args, env=None):
    e = {**os.environ}
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    e.pop("EASYCIRQ_ENTERPRISE_HITS", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(ROOT), env=e)


def test_check_writes_hits_and_report_shows_them():
    """端到端：跑一次违规板 → 计数写盘 → 报告里出现次数。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1", "rules": [a_rule()]},
            ensure_ascii=False), encoding="utf-8")
        hits = tmp / "hits.json"
        nl = tmp / "bad.json"
        nl.write_text(json.dumps(board("R0402")), encoding="utf-8")

        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
               "EASYCIRQ_ENTERPRISE_HITS": str(hits)}
        p = run("enterprise_rules.py", ["--netlist", str(nl)], env)
        assert p.returncode == 1, p.stdout[-600:]
        assert hits.is_file(), "跑完没有写下计数"
        data = json.loads(hits.read_text(encoding="utf-8"))
        assert data["no-0402"]["count"] == 1

        out = tmp / "kb.html"
        r = run("enterprise_kb.py", ["--out", str(out)], env)
        assert r.returncode == 0, r.stdout[-600:]
        text = out.read_text(encoding="utf-8")
        assert "本机拦截次数" in text
        assert "1 次" in text
        assert "不是公司汇总" in text, "必须说清这是本机记录"


def test_report_says_no_record_when_never_fired():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1", "rules": [a_rule()]},
            ensure_ascii=False), encoding="utf-8")
        out = tmp / "kb.html"
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
               "EASYCIRQ_ENTERPRISE_HITS": str(tmp / "hits.json")}
        run("enterprise_kb.py", ["--out", str(out)], env)
        text = out.read_text(encoding="utf-8")
    assert "无记录" in text, "从没拦过要明说，不能留空"
