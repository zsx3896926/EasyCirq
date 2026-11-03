"""验收单里的命令必须真能跑、真能给出它承诺的结果。

原则和演示文档一样：文档写过的东西，测试要照着跑一遍。
验收单更要紧——客户会拿着它签字。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "delivery-acceptance.md"
EC = ["easycirq", "enterprise"]

RULE = {
    "schema": "easycirq-enterprise-rules/v1",
    "rules": [{
        "id": "no-0402", "kind": "hard", "title": "禁用 0402 封装",
        "predicate": {"type": "footprint_forbidden", "patterns": ["0402"]},
        "evidence": "产线贴片下限 0603（DS-2024-07 §3.2）",
        "owner": "硬件部 张工",
        "verified_on": "在一块 R0402 的板子上跑过，报 fail",
    }]}


def board(fp):
    return {"components": [
        {"designator": "R1", "componentType": "part",
         "footprintRef": {"name": fp}, "otherProperty": {},
         "pins": [{"pinNumber": "1", "net": "A"},
                  {"pinNumber": "2", "net": "B"}]},
    ]}


def run(args, cwd, env=None):
    e = {**os.environ}
    for k in ("EASYCIRQ_KNOWLEDGE_DIR", "EASYCIRQ_ENTERPRISE_HITS"):
        e.pop(k, None)
    if env:
        e.update(env)
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=180, cwd=str(cwd), env=e)


@pytest.fixture()
def env(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "rules.company.json").write_text(
        json.dumps(RULE, ensure_ascii=False), encoding="utf-8")
    e = {"EASYCIRQ_KNOWLEDGE_DIR": str(lib),
         "EASYCIRQ_ENTERPRISE_HITS": str(tmp_path / "hits.json")}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(board("R0402")), encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(json.dumps(board("R0603")), encoding="utf-8")
    return {"env": e, "tmp": tmp_path, "bad": bad, "good": good}


# ── 文档结构：四件事必须齐 ──────────────────────────────────────────────

def test_doc_has_all_ten_items():
    s = DOC.read_text(encoding="utf-8")
    for i in range(1, 11):
        assert f"### 第 {i} 项" in s, f"缺第 {i} 项"


def test_doc_has_three_party_signoff_and_exit_criteria():
    s = DOC.read_text(encoding="utf-8")
    assert "客户方验收人" in s, "没有签字栏"
    assert "中止的定义" in s, "没有中止条件"
    assert "成功的定义" in s, "没有成功条件"


def test_doc_states_what_is_not_verified():
    s = DOC.read_text(encoding="utf-8")
    assert "不能在这张单子里验的" in s
    for must in ("私有部署", "真实 LLM 调用", "未达成"):
        assert must in s, f"未验项缺 {must}"


# ── 第 3 项：库能加载 ──────────────────────────────────────────────────

def test_item3_list_shows_rules(env):
    p = run(EC + ["ls"], env["tmp"], env["env"])
    assert p.returncode == 0, p.stdout[-400:]
    assert "no-0402" in p.stdout


# ── 第 4 项：拦住违规板，退出码 1，指名道姓 ────────────────────────────

def test_item4_check_fails_with_exit_1_and_names_the_part(env):
    p = run(EC + ["check", "--netlist", str(env["bad"])], env["tmp"], env["env"])
    assert p.returncode == 1, p.stdout[-400:]
    assert "fail" in p.stdout.lower()
    assert "R1" in p.stdout and "R0402" in p.stdout, "没指名道姓"


# ── 第 5 项：合规板通过，退出码 0 ──────────────────────────────────────

def test_item5_clean_board_passes_with_exit_0(env):
    p = run(EC + ["check", "--netlist", str(env["good"])], env["tmp"], env["env"])
    assert p.returncode == 0, p.stdout[-400:]
    assert "pass" in p.stdout.lower()


# ── 第 6 项：三件事同时出现 ────────────────────────────────────────────

def test_item6_review_names_violation_evidence_and_owner(env):
    p = run(EC + ["review", "--netlist", str(env["bad"])], env["tmp"], env["env"])
    assert p.returncode == 1
    for must in ("违反", "依据", "找谁"):
        assert must in p.stdout, f"缺 {must}：\n{p.stdout[-600:]}"


# ── 第 7 项：报告自包含 + 无记录 + 问题区 ──────────────────────────────

def test_item7_report_is_self_contained(env):
    out = env["tmp"] / "kb.html"
    p = run(EC + ["report", "--out", str(out)], env["tmp"], env["env"])
    assert p.returncode == 0, p.stdout[-400:]
    text = out.read_text(encoding="utf-8")
    for bad in ("http://", "https://", "<script", "@import", "src=", "<link", "cdn"):
        assert bad not in text, f"引了外部资源：{bad}"
    for section in ("可执行规则", "可检索知识", "企业器件参数", "读了哪些文件"):
        assert section in text
    assert "本机拦截次数" in text
    assert "不是公司汇总" in text
    # 没拦过的规则要显示「无记录」
    assert "无记录" in text


# ── 第 9 项：凭据里没有密钥 ────────────────────────────────────────────

def test_item9_credentials_hold_no_llm_key(tmp_path):
    cred = tmp_path / "cred.json"
    e = {**os.environ, "EASYCIRQ_CREDENTIALS": str(cred)}
    # 未登录状态：不该凭空出现任何东西
    p = subprocess.run(["easycirq", "login", "--status"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, env=e)
    assert p.returncode == 0
    assert not cred.is_file() or "sk-" not in cred.read_text(encoding="utf-8")


def test_item1_doctor_is_runnable(env):
    """第 1 项要求 doctor 能跑并给出结论。这里只验它可执行、有明确 verdict。"""
    p = subprocess.run(["easycirq", "doctor"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    assert "verdict" in (p.stdout or "") + (p.stderr or "")


def test_item2_connector_verify_is_runnable():
    p = subprocess.run(["easycirq", "connector", "verify"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    out = (p.stdout or "") + (p.stderr or "")
    assert "expectedVersion" in out or "loadedWindows" in out


# ── 第 8 项：两人维护不互相覆盖 ────────────────────────────────────────

def test_item8_two_promotes_keep_both(env):
    tmp = env["tmp"]
    lib = tmp / "lib"

    def ledger(name, rule_id):
        p = tmp / f"{name}.json"
        p.write_text(json.dumps({
            "schema": "easycirq-review-ledger/v1",
            "entries": [{"id": name, "reviewer": "张工", "found": "x",
                         "disposition": "rule",
                         "rule": {"id": rule_id, "kind": "hard",
                                  "title": rule_id,
                                  "predicate": {"type": "footprint_forbidden",
                                                "patterns": ["0402"]},
                                  "evidence": "e", "verified_on": "v"}}]},
            ensure_ascii=False), encoding="utf-8")
        return p

    for name, rid in (("A", "rule-a"), ("B", "rule-b")):
        p = run(EC + ["promote", "--ledger", str(ledger(name, rid))],
                tmp, env["env"])
        assert p.returncode == 0, p.stdout[-500:]

    data = json.loads((lib / "rules.from-review.json").read_text(encoding="utf-8"))
    ids = sorted(r["id"] for r in data["rules"])
    assert "rule-a" in ids and "rule-b" in ids, f"互相覆盖了：{ids}"
