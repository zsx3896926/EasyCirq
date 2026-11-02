"""补验：verifier 点名的几处缺口。

① 企业层优先级高于内置层（同键，字段级来源可见）
② 损坏的企业文件，报错必须点出**读了哪一份**
③ 「规则不许降级成知识」——knowledge 条目必须写 why_not_rule
④ 「知识不许伪装成规则」——标 rule 但谓词执行不了必须被拒
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


def run(script, args, env=None, cwd=None):
    e = {**os.environ}
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180,
                       cwd=str(cwd or ROOT), env=e)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ── ① 企业层覆盖内置层
def test_enterprise_layer_overrides_builtin_field_by_field():
    """同一个键：measured 来自企业层，desc/deviceUuid 仍来自内置层。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "lib"
        lib.mkdir()
        (lib / "parts.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-parts/v1",
            "parts": {"mosfet.ao3400a_sot23": {
                "value": "AO3400A", "mpn": "AO3400A",
                "measured": {"vgs_th": 1.3}}}}, ensure_ascii=False),
            encoding="utf-8")
        rc, out = run("enterprise_parts.py",
                      ["--resolve", "mosfet.ao3400a_sot23", "--json"],
                      env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert rc == 0, out[-600:]
    rep = json.loads(out[out.find("{"):])
    origin = rep["origin"]
    assert origin["measured"] != "builtin", "实测值没取企业层的"
    assert (rep["effective"]["measured"] or {}).get("vgs_th") == 1.3
    assert origin["desc"] == "builtin", "企业没写的字段应当仍是内置的"
    assert origin["deviceUuid"] == "builtin"


# ── ② 损坏文件要说清读了哪一份
def test_corrupt_file_error_names_the_full_path():
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "lib"
        lib.mkdir()
        bad = lib / "rules-broken.json"
        bad.write_text("{ 这不是合法 JSON ", encoding="utf-8")
        rc, out = run("enterprise_selfcheck.py", [],
                      env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert rc == 1, out[-600:]
    assert str(bad) in out, "报错没点出完整文件路径"
    assert "读不出来" in out


def test_describe_lists_every_layer_it_looked_at():
    """--describe 要把每个层读了哪个目录、几个文件都列出来。"""
    with tempfile.TemporaryDirectory() as tmp:
        lib = pathlib.Path(tmp) / "lib"
        lib.mkdir()
        (lib / "r.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [{"id": "r1", "kind": "hard", "title": "t",
                       "predicate": {"type": "footprint_forbidden",
                                     "patterns": ["0402"]},
                       "evidence": "e", "verified_on": "v"}]},
            ensure_ascii=False), encoding="utf-8")
        rc, out = run("enterprise_rules.py", ["--describe"],
                      env={"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
    assert rc == 0, out[-600:]
    assert str(lib) in out, "没列出企业目录"
    assert "enterprise(env)" in out
    assert "r.json" in out, "没列出具体文件名"


# ── ③ 规则不许降级成知识
def _ledger(tmp, entries):
    p = pathlib.Path(tmp) / "ledger.json"
    p.write_text(json.dumps({"schema": "easycirq-review-ledger/v1",
                             "entries": entries}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def test_knowledge_without_why_not_rule_is_rejected():
    """标成 knowledge 却没说明为什么不能自动化 → 必须拒绝。

    工具判断不了"这事本可自动查"，但能要求人**写清理由**，
    防止把能自动查的东西随手降级成知识。
    """
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _ledger(tmp, [{
            "id": "K-1", "reviewer": "李工", "found": "某经验",
            "disposition": "knowledge",
            "knowledge": {"title": "t", "body": "b"},
        }])
        rc, out = run("review_ledger.py", ["--ledger", str(ledger), "--verify"])
    assert rc == 2, out[-600:]
    assert "why_not_rule" in out


def test_knowledge_with_why_not_rule_passes():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _ledger(tmp, [{
            "id": "K-1", "reviewer": "李工", "found": "某经验",
            "disposition": "knowledge",
            "knowledge": {"title": "t", "body": "b",
                          "why_not_rule": "依赖供应商口头承诺，图纸里没有这个字段"},
        }])
        rc, out = run("review_ledger.py", ["--ledger", str(ledger), "--verify"])
    assert rc == 0, out[-600:]


# ── ④ 知识不许伪装成规则
def test_rule_with_unexecutable_predicate_is_rejected_and_told_to_use_knowledge():
    """标了 rule 但写不成判据 → 必须拒，并提示改标 knowledge。"""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _ledger(tmp, [{
            "id": "R-1", "reviewer": "张工", "found": "去耦太远",
            "disposition": "rule",
            "rule": {"id": "decap", "kind": "hard",
                     "predicate": {"type": "distance_too_far"},
                     "evidence": "e", "verified_on": "v"},
        }])
        rc, out = run("review_ledger.py", ["--ledger", str(ledger), "--verify"])
    assert rc == 2, out[-700:]
    assert "不可执行" in out
    assert "knowledge" in out, "没提示可以改标 knowledge"


def test_disposition_is_mandatory():
    """不选边直接拒——工具不替人判断规则还是知识。"""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _ledger(tmp, [{
            "id": "X-1", "reviewer": "张工", "found": "某意见",
        }])
        rc, out = run("review_ledger.py", ["--ledger", str(ledger), "--verify"])
    assert rc == 2, out[-600:]
    assert "必须显式选边" in out
