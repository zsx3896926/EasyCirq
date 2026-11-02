"""企业器件库：实测参数要**真的被判据用上**，不是存起来。

这个模块存在的理由就是让企业实测值生效。所以每条测试都盯着
「判据的输出里有没有用上这个数、且说不说得出来源」。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARTS_TOOL = ROOT / "easycirq" / "scripts" / "enterprise_parts.py"
DV = ROOT / "easycirq" / "scripts" / "sch_design_validity.py"
EXAMPLE = ROOT / "examples" / "enterprise-knowledge" / "parts.company.json"


def run(tool, args, env=None):
    e = dict(os.environ)
    e.pop("EASYCIRQ_KNOWLEDGE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(tool), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(ROOT), env=e)


def board():
    return {"components": [
        {"designator": "U1", "componentType": "part", "otherProperty": {},
         "manufacturerId": "LM393",
         "pins": [{"pinNumber": "1", "net": "GATE"}, {"pinNumber": "8", "net": "PWR5V"},
                  {"pinNumber": "4", "net": "GND"}]},
        {"designator": "R5", "componentType": "part",
         "otherProperty": {"Value": "100kΩ"},
         "pins": [{"pinNumber": "1", "net": "PWR5V"}, {"pinNumber": "2", "net": "GATE"}]},
        {"designator": "Q1", "componentType": "part", "manufacturerId": "AO3400",
         "otherProperty": {},
         "pins": [{"pinNumber": "1", "pinName": "G", "net": "GATE"},
                  {"pinNumber": "2", "pinName": "S", "net": "GND"},
                  {"pinNumber": "3", "pinName": "D", "net": "FAN_M"}]},
        {"designator": "FAN1", "componentType": "part", "otherProperty": {},
         "manufacturerId": "FAN-12V",
         "pins": [{"pinNumber": "1", "pinName": "+", "net": "PWR12V"},
                  {"pinNumber": "2", "pinName": "-", "net": "FAN_M"}]},
        {"designator": "D1", "componentType": "part", "manufacturerId": "1N4148",
         "otherProperty": {},
         "pins": [{"pinNumber": "1", "pinName": "K", "net": "PWR12V"},
                  {"pinNumber": "2", "pinName": "A", "net": "FAN_M"}]},
    ]}


def intent(vgs_th=None, part_key=None):
    sw = {"part": "Q1", "load": "FAN1", "load_ma": 200, "kind": "mosfet",
          "load_kind": "inductive", "load_rail": "PWR12V"}
    if vgs_th is not None:
        sw["vgs_th"] = vgs_th
    if part_key:
        sw["part_key"] = part_key
    return {"schema": "easycirq-design-intent/v1", "power_rail": "PWR5V",
            "load_rail": "PWR12V", "ground": "GND",
            "rails": {"PWR5V": 5.0, "PWR12V": 12.0}, "grounds": ["GND"],
            "switches": [sw]}


def run_dv(tmpdir, intent_obj, enterprise=None):
    nl = pathlib.Path(tmpdir) / "list.json"
    nl.write_text(json.dumps(board(), ensure_ascii=False), encoding="utf-8")
    it = pathlib.Path(tmpdir) / "intent.json"
    it.write_text(json.dumps(intent_obj, ensure_ascii=False), encoding="utf-8")
    args = ["--netlist", str(nl), "--intent", str(it)]
    if enterprise:
        args += ["--enterprise-parts", str(enterprise)]
    return run(DV, args)


def test_resolve_shows_which_layer_each_field_came_from():
    proc = run(PARTS_TOOL, ["--parts", str(EXAMPLE),
                            "--resolve", "mosfet.ao3400a_sot23", "--json"])
    assert proc.returncode == 0, proc.stdout[-600:]
    report = json.loads(proc.stdout[proc.stdout.find("{"):])
    origin = report["origin"]
    # 实测值来自企业层；企业没写的字段（basic/desc）仍来自内置层
    assert origin["measured"] != "builtin"
    assert origin["basic"] == "builtin", origin


def test_measured_vgs_th_is_actually_used_by_the_check():
    """意图不写 vgs_th，只给 part_key → 判据必须用企业实测的 1.3V。"""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_dv(tmp, intent(part_key="mosfet.ao3400a_sot23"), EXAMPLE)
        assert '"vgs_th": 1.3' in proc.stdout, proc.stdout[-800:]
        assert "企业实测" in proc.stdout, "用了企业值却不说来源"


def test_intent_declaration_wins_and_disagreement_is_flagged():
    """意图显式值优先；与企业实测差得多时要提示（不阻断）。"""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_dv(tmp, intent(vgs_th=2.0, part_key="mosfet.ao3400a_sot23"),
                      EXAMPLE)
        assert '"vgs_th": 2.0' in proc.stdout
        assert "意图声明" in proc.stdout
        assert "VGS_TH_DISAGREES_WITH_MEASURED" in proc.stdout
        # advisory 不改变整体判定
        assert "设计有效性：pass" in proc.stdout


def test_without_enterprise_library_it_falls_back_and_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_dv(tmp, intent(part_key="mosfet.ao3400a_sot23"), None)
        assert '"vgs_th": 1.5' in proc.stdout
        assert "内置默认" in proc.stdout


def test_missing_explicit_parts_path_is_reported():
    proc = run(PARTS_TOOL, ["--parts", "no/such/parts.json"])
    assert proc.returncode != 0
    out = proc.stdout + (proc.stderr or "")
    assert "不存在" in out
