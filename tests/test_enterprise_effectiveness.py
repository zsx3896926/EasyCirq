"""补验：报告要能看出「哪些从未生效」，以及人审不可绕过。"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import review_ledger  # noqa: E402


def run(script, args, env=None):
    e = {**os.environ}
    for k in ("EASYCIRQ_KNOWLEDGE_DIR", "EASYCIRQ_ENTERPRISE_HITS"):
        e.pop(k, None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(ROOT), env=e)


def rule(rid):
    return {"id": rid, "kind": "hard", "title": f"规则 {rid}",
            "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
            "evidence": "e", "owner": "硬件部", "verified_on": "跑过"}


def board(fp="R0402"):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": fp}, "otherProperty": {},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def test_report_distinguishes_fired_from_never_fired():
    """拦过的规则显示次数；从没拦到的显示「无记录」。两者不许混。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [rule("rule-fired"), rule("rule-never")]}, ensure_ascii=False),
            encoding="utf-8")

        hits = tmp / "hits.json"
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
               "EASYCIRQ_ENTERPRISE_HITS": str(hits)}

        # 只让 rule-fired 命中一次：造一条只违反它的规则？
        # 两条规则谓词相同，都会命中；所以用两次不同的板把计数拉开：
        # 先跑一次违规板 -> 两条都计一次；再手工把 rule-never 从计数里去掉。
        bad = tmp / "bad.json"
        bad.write_text(json.dumps(board("R0402")), encoding="utf-8")
        run("enterprise_rules.py", ["--netlist", str(bad)], env)

        data = json.loads(hits.read_text(encoding="utf-8"))
        assert "rule-fired" in data and "rule-never" in data
        data.pop("rule-never")
        hits.write_text(json.dumps(data), encoding="utf-8")

        out = tmp / "kb.html"
        p = run("enterprise_kb.py", ["--out", str(out)], env)
        assert p.returncode == 0, p.stdout[-600:]
        text = out.read_text(encoding="utf-8")

    assert "本机拦截次数" in text
    assert "1 次" in text, "拦过的规则要显示次数"
    assert "无记录" in text, "从没拦到的规则要显示「无记录」而不是 0"
    # 那句口径说明必须在，否则别人会当成公司汇总
    assert "不是公司汇总" in text


def test_report_lists_entries_that_never_took_effect():
    """缺 verified_on 的规则、永远检索不到的知识，都要进问题区。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        no_ev = rule("rule-no-evidence")
        no_ev.pop("verified_on")
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [no_ev]}, ensure_ascii=False), encoding="utf-8")
        (lib / "kb.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-knowledge/v1",
            "knowledge": [{"id": "K-DEAD", "title": "", "body": "", "tags": [],
                           "why_not_rule": "x"}]}, ensure_ascii=False),
            encoding="utf-8")

        out = tmp / "kb.html"
        env = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
               "EASYCIRQ_ENTERPRISE_HITS": str(tmp / "hits.json")}
        run("enterprise_kb.py", ["--out", str(out)], env)
        text = out.read_text(encoding="utf-8")

    assert "不会生效" in text
    assert "没有 verified_on" in text
    assert "K-DEAD" in text


# ── 人审不可绕过 ────────────────────────────────────────────────────────

def test_entry_without_disposition_cannot_be_promoted():
    """没写 disposition 的条目推不进去。

    这是「人审不可被平台化抹掉」在代码层的落点：
    必须有人明确判定它是规则还是知识，工具不替他决定。
    """
    ledger = {"schema": "easycirq-review-ledger/v1", "entries": [{
        "id": "X-1", "reviewer": "张工", "found": "某意见"}]}
    with tempfile.TemporaryDirectory() as tmp:
        r = review_ledger.promote(ledger, pathlib.Path(tmp) / "lib")
    assert r["ok"] is False
    assert any("必须显式选边" in p for p in r["problems"]), r["problems"]


def test_rule_without_verified_on_cannot_be_promoted():
    """没写 verified_on 的规则推不进去——没人背书它有用。"""
    ledger = {"schema": "easycirq-review-ledger/v1", "entries": [{
        "id": "R-1", "reviewer": "张工", "found": "x",
        "disposition": "rule",
        "rule": {"id": "r1", "kind": "hard", "title": "t",
                 "predicate": {"type": "footprint_forbidden",
                               "patterns": ["0402"]},
                 "evidence": "e"}}]}
    with tempfile.TemporaryDirectory() as tmp:
        r = review_ledger.promote(ledger, pathlib.Path(tmp) / "lib")
    assert r["ok"] is False
    assert any("verified_on" in p for p in r["problems"]), r["problems"]


def test_review_never_says_approved_only_pass_or_fail():
    """review 的结论只有「有没有违反」和「判不判得了」，没有「批准」。

    平台不该提供一个让人点一下就代表签字的结论——签字是人做的事。
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "rules.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-rules/v1",
            "rules": [rule("r1")]}, ensure_ascii=False), encoding="utf-8")
        good = tmp / "good.json"
        good.write_text(json.dumps(board("R0603")), encoding="utf-8")
        p = run("enterprise_review.py", ["--netlist", str(good)],
                {"EASYCIRQ_KNOWLEDGE_DIR": str(lib)})
        out = p.stdout

    assert "没有违反已知的企业规范" in out
    # 这些词都不该出现：平台不签发批准
    for forbidden in ("已批准", "批准交付", "自动通过", "无需人工"):
        assert forbidden not in out, f"review 出现了「{forbidden}」——平台不该签发批准"
