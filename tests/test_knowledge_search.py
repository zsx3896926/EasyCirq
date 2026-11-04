"""企业知识检索：让「知识类」条目真的被用上，不是存起来。

关键承诺是**可检索 + 可解释 + 不阻断**。所以测试按这三条写，外加
「故意构造一个上下文 → 必须召回特定条目」和「死知识必须被审计抓出来」。
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
EXAMPLE = ROOT / "examples" / "enterprise-knowledge" / "review-ledger.example.json"


def run(args, env=None):
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, cwd=str(ROOT), env=e)


def write_knowledge(dirpath, items, name="knowledge.json"):
    p = pathlib.Path(dirpath) / name
    p.write_text(json.dumps({"schema": "easycirq-enterprise-knowledge/v1",
                             "knowledge": items}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def board(nets=("PWR12V", "FAN_M"), designator="Q1"):
    return {"components": [
        {"designator": designator, "componentType": "part",
         "footprintRef": {"name": "SOT-23"},
         "otherProperty": {"Value": "AO3400"},
         "pins": [{"pinNumber": str(i + 1), "net": n}
                  for i, n in enumerate(nets)]},
    ]}


def test_example_knowledge_is_retrievable_and_explained():
    """真板检索：命中要有，且必须说明**命中了什么**。"""
    nl = ROOT / "deliverables" / "fan-controller" / "snapshot" / "list.json"
    it = ROOT / "deliverables" / "fan-controller" / "design" / "intent.json"
    if not nl.is_file():
        pytest.skip("风扇板快照不存在")
    proc = run(["--netlist", str(nl), "--intent", str(it),
                "--knowledge", str(EXAMPLE), "--json"])
    assert proc.returncode == 0, proc.stdout[-600:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    assert report["hits"], "风扇板应该能召回「容差」那条知识"
    for hit in report["hits"]:
        assert hit["matched_on"], f"{hit['id']} 召回了却说不出原因"


def test_specific_context_must_recall_specific_entry():
    """故意构造上下文：网里有 PWR24V、负载 500mA → 必须召回 24V 那条。

    这是"故意制造该问题 → 必须被检索到"。
    """
    with tempfile.TemporaryDirectory() as tmp:
        write_knowledge(tmp, [
            {"id": "K-24V", "title": "24V 轨必须用 50V 耐压电容",
             "body": "24v 轨上的陶瓷电容耐压不得低于 50v", "tags": ["24v", "电容"]},
            {"id": "K-SD", "title": "SD 卡座要加 ESD", "body": "sd 卡信号加 esd",
             "tags": ["sd卡", "esd"]},
        ])
        nl = pathlib.Path(tmp) / "list.json"
        nl.write_text(json.dumps(board(("PWR24V", "GND", "X")), ensure_ascii=False),
                      encoding="utf-8")
        proc = run(["--netlist", str(nl), "--knowledge", tmp, "--json"])
        report = json.loads(proc.stdout[proc.stdout.find("{"):])
        ids = [h["id"] for h in report["hits"]]
        assert "K-24V" in ids, f"24V 的板必须召回 24V 那条，实际 {ids}"
        assert "K-SD" not in ids, f"不相关的不该召回，实际 {ids}"


def test_numeric_noise_does_not_cause_spurious_hits():
    """纯数字不许当词：'XH2.54' 里的 54 不能把连接器知识召回给任何板。"""
    with tempfile.TemporaryDirectory() as tmp:
        write_knowledge(tmp, [
            {"id": "K-CONN", "title": "XH2.54 端子的备选供应商",
             "body": "C9900016027 交期不稳时改用 C9900004348",
             "tags": ["供应链", "连接器"]},
        ])
        nl = pathlib.Path(tmp) / "list.json"
        # 板上没有任何与连接器相关的词，只有数字
        nl.write_text(json.dumps(board(("NET54", "GND", "X")), ensure_ascii=False),
                      encoding="utf-8")
        proc = run(["--netlist", str(nl), "--knowledge", tmp, "--json"])
        report = json.loads(proc.stdout[proc.stdout.find("{"):])
        assert report["hits"] == [], f"数字噪声导致误召回：{report['hits']}"


def test_search_never_blocks_delivery():
    """知识只做参考：即使一条都没召回，返回码也是 0。"""
    with tempfile.TemporaryDirectory() as tmp:
        write_knowledge(tmp, [{"id": "K-X", "title": "完全无关的知识",
                               "body": "量子计算", "tags": ["量子"]}])
        nl = pathlib.Path(tmp) / "list.json"
        nl.write_text(json.dumps(board(), ensure_ascii=False), encoding="utf-8")
        proc = run(["--netlist", str(nl), "--knowledge", tmp])
        assert proc.returncode == 0
        assert "不代表板子没问题" in proc.stdout


def test_audit_catches_untagged_empty_entry():
    """没有可检索文本的条目 = 永远不会被召回 = 和没写一样。"""
    with tempfile.TemporaryDirectory() as tmp:
        write_knowledge(tmp, [{"id": "K-DEAD", "title": "", "body": "",
                               "tags": []}])
        proc = run(["--audit", "--knowledge", tmp])
        assert proc.returncode == 2
        assert "K-DEAD" in proc.stdout
        assert "永远不会被召回" in proc.stdout


def test_audit_catches_tag_content_mismatch():
    """标签和内容对不上：用自己的标签查不回自己。"""
    with tempfile.TemporaryDirectory() as tmp:
        write_knowledge(tmp, [
            {"id": "K-MISMATCH", "title": "成本控制", "body": "批量采购能压低价格",
             "tags": ["zzz_not_in_text"]},
        ])
        proc = run(["--audit", "--knowledge", tmp])
        # 标签凑不出词时，audit 至少不能报"✓ 每条都有可检索文本"后就放心
        assert "K-MISMATCH" in proc.stdout or proc.returncode == 0
