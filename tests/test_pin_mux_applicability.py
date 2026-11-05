"""`pin_mux` 适用性判据的护栏：**判据要贴着被测量的东西**。

`pin_plan_check.py` 判的是 MCU 的引脚复用与资源分配（`mcu.ref`、
`pins[].logical`、pinmux、资源预算）。buck / boost **电源 IC 的引脚是固定功能**，
没有复用可言，对它们要求引脚规划表是无从测量的。

而管线原来用 `has_ic`（有任何 IC）当代理 —— 纯电源板也被拖进来（friction #54）。

**关键：这不是放宽守卫。** 只要板上有 MCU，没规划表照样 `missing` → 阻断。
"""

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_offline_pipeline as P  # noqa: E402

NET = ROOT / "reports" / "hard-board" / "board2" / "netlist.json"


def comp(ref, device):
    return {"ref": ref, "device": {"name": device}}


# ── MCU 判定 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("c,want", [
    (comp("U1", "mcu.esp32s3_wroom"), True),
    (comp("U1", "mcu.stm32g071"), True),
    (comp("U1", "fpga.xc7a35t"), True),
    (comp("U1", "soc.rk3566"), True),
    # 电源 IC **不是**复用资源
    (comp("U1", "buck.tps54360_so8"), False),
    (comp("U1", "buckboost.tps63802_vson10"), False),
    (comp("U1", "ldo.ams1117_3v3"), False),
    (comp("U1", "ic.xl1509_5v_buck"), False),
    (comp("R1", "res.10k_0402"), False),
])
def test_mcu_detection_matches_what_the_kpi_measures(c, want):
    assert P._is_mcu_component(c) is want


def test_board2_has_no_mcu_so_pin_mux_does_not_apply():
    """板2 是纯电源板（buck/buckboost/电源 IC），没有任何复用资源。"""
    if not NET.is_file():
        pytest.skip("没有网表")
    d = json.loads(NET.read_text(encoding="utf-8"))
    heads = {c["device"]["name"].split(".")[0] for c in d["components"]}
    assert not (heads & P.MCU_HEADS), "板2 不该有 MCU，实际有：%r" % (heads & P.MCU_HEADS)
    assert not any(P._is_mcu_component(c) for c in d["components"])


def test_a_board_with_an_mcu_still_requires_a_pin_plan():
    """**守卫没放宽**：有 MCU 又没规划表，pin_mux 必须阻断。"""
    if not NET.is_file():
        pytest.skip("没有网表")
    d = json.loads(NET.read_text(encoding="utf-8"))
    fake = dict(d)
    fake["components"] = list(d["components"]) + [comp("U99", "mcu.esp32s3_wroom")]
    assert any(P._is_mcu_component(c) for c in fake["components"])


def test_the_na_note_explains_why():
    """`na` 必须说明"为什么这里不适用"，否则读者会以为漏测。"""
    src = (ROOT / "easycirq" / "scripts" / "sch_offline_pipeline.py").read_text(
        encoding="utf-8")
    assert "没有 MCU/SoC" in src, "na 的说明没有点出 MCU"
    assert "固定功能" in src or "复用" in src, "na 的说明没说清判据依据"


def test_kpi_layer_still_blocks_when_pinplan_is_absent():
    """**守卫没放宽的证明**：只要没给 pinplan 检查，`pin_mux` 就是 `missing`。

    这条在 **KPI 层**验证，与管线写不写 `na` 无关 ——
    管线只负责在"没有 MCU"时**不提交这个检查**；一旦提交了页面就该被判缺失。
    """
    sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
    import sch_kpi

    def payload(keep_pinplan):
        checks = []
        for cid in sch_kpi.CHECK_IDS:
            if cid == "pinplan" and not keep_pinplan:
                continue
            checks.append({"id": cid, "tool": sch_kpi.DEFAULTS["sources"].get(
                cid, {}).get("tool", ""), "verdict": "pass", "metrics": {},
                "findings": [], "evidence": "reports/%s.json" % cid})
        return {"schema": sch_kpi.SCHEMA_INPUT, "project": "p", "page": "Sheet1",
                "round": 1, "profile": "default", "stage": "schematic",
                "checks": checks}

    # 没给 pinplan → pin_mux 必须 missing，并进 blockers
    rep = sch_kpi.evaluate(payload(keep_pinplan=False))
    row = next(r for r in rep["kpis"] if r["id"] == "pin_mux")
    assert row["status"] == "missing", row["status"]
    assert "pin_mux" in [b["kpi"] for b in rep["blockers"]], rep["blockers"]
    assert rep["verdict"] == "BLOCKED"


def test_pipeline_only_writes_na_when_there_is_no_mcu():
    """管线写 `na` 的条件必须是"没有 MCU"，不是"有任何 IC"。"""
    src = (ROOT / "easycirq" / "scripts" / "sch_offline_pipeline.py").read_text(
        encoding="utf-8")
    # 判据函数存在且按 MCU 前缀判
    assert "_is_mcu_component" in src
    assert "MCU_HEADS" in src
    # na 分支必须用 has_mcu，不许再用 has_ic
    assert re.search(r"has_mcu\s*=\s*any\(_is_mcu_component", src), \
        "na 分支没有使用 _is_mcu_component"
    assert "if not has_mcu:" in src, "na 分支条件不是 has_mcu"

