"""概念派生层：让「板子明明是感性负载，那条续流知识却搜不到」这种失效不再发生。

这一层是同义词表，不是语义理解——所以测试只钉「表里列出的映射必须生效」，
不假装它能覆盖所有说法。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "easycirq" / "scripts" / "knowledge_search.py"
NL = ROOT / "deliverables" / "fan-controller" / "snapshot" / "list.json"
IT = ROOT / "deliverables" / "fan-controller" / "design" / "intent.json"


def search(knowledge, netlist=None, intent=None):
    with tempfile.TemporaryDirectory() as tmp:
        pathlib.Path(tmp, "kb.json").write_text(json.dumps({
            "schema": "easycirq-enterprise-knowledge/v1",
            "knowledge": knowledge}, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ}
        env.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
        args = [sys.executable, str(TOOL), "--knowledge", tmp, "--json"]
        if netlist:
            args += ["--netlist", str(netlist)]
        if intent:
            args += ["--intent", str(intent)]
        p = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180,
                           env=env, cwd=str(ROOT))
        out = p.stdout or ""
        return json.loads(out[out.find("{"):])


FLYBACK = {
    "id": "K-FLYBACK", "title": "感性负载必须续流",
    "body": "继电器、风扇、电机这类感性负载，关断时会产生反向尖峰，必须并联续流二极管。",
    "tags": ["驱动", "感性负载"],
}


@pytest.mark.skipif(not (NL.is_file() and IT.is_file()), reason="风扇板快照不存在")
def test_inductive_board_recalls_flyback_knowledge():
    """风扇板是感性负载 —— 那条续流知识必须被召回。

    这是 2026-11-03 实测发现的失效：板子上下文写的是英文 `inductive`，
    客户写的是中文「感性负载」，一个词都不重合，最该命中的那条召回不到。
    """
    rep = search([FLYBACK], NL, IT)
    ids = [h["id"] for h in rep["hits"]]
    assert "K-FLYBACK" in ids, f"感性负载的板没召回续流知识：{ids}"
    hit = next(h for h in rep["hits"] if h["id"] == "K-FLYBACK")
    assert hit["matched_on"], "召回了却说不出命中什么"


def test_connector_concept_fires_for_a_board_with_a_connector():
    """有 J* 连接器的板要能召回接口保护知识——证明这条映射不是死代码。"""
    board = {"components": [
        {"designator": "J1", "componentType": "part",
         "pins": [{"pinNumber": "1", "net": "PWR5V"},
                  {"pinNumber": "2", "net": "GND"}]},
    ]}
    esd = {"id": "K-ESD", "title": "对外接口要加 TVS",
           "body": "所有出机壳的连接器都要加 tvs 管，否则静电打坏主控。",
           "tags": ["保护"]}
    with tempfile.TemporaryDirectory() as tmp:
        nl = pathlib.Path(tmp) / "list.json"
        nl.write_text(json.dumps(board), encoding="utf-8")
        rep = search([esd], nl, None)
    ids = [h["id"] for h in rep["hits"]]
    assert "K-ESD" in ids, f"有连接器的板没召回接口保护知识：{ids}"


def test_unrelated_knowledge_is_still_not_recalled():
    """派生概念不能让什么都命中——无关的知识必须仍然召回不到。"""
    supply = {"id": "K-SUPPLY", "title": "某料交期记录",
              "body": "C0000000 这个料 2026 年 3 月交期 12 周。",
              "tags": ["供应链"]}
    if not (NL.is_file() and IT.is_file()):
        pytest.skip("风扇板快照不存在")
    rep = search([supply], NL, IT)
    ids = [h["id"] for h in rep["hits"]]
    assert "K-SUPPLY" not in ids, f"无关知识被误召回：{ids}"


def test_derived_concepts_are_reported_in_context():
    """上下文要如实说出补了哪些概念——不然召回原因不可解释。"""
    if not (NL.is_file() and IT.is_file()):
        pytest.skip("风扇板快照不存在")
    rep = search([FLYBACK], NL, IT)
    joined = "；".join(rep.get("context") or [])
    assert "补入" in joined, f"上下文没说明补了什么概念：{joined[:200]}"
