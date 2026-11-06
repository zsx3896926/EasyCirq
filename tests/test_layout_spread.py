"""铺开能力的回归测试。

钉住两件本轮踩出来的事：
  1. **只给信号网相连的外设加附着提示** —— 电源/地相连的一加就
     `peripheral-direct-missing`（去耦电容就是这种）
  2. **选间距按两向填充**（min(宽比,高比)），不是按最宽 ——
     否则会选出 355×75 那种细长条，横 60% 纵 18%，更难看
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_spread as S  # noqa: E402

ONE_M3 = ROOT / "reports" / "hard-board" / "board2" / "one-M3.json"


@pytest.mark.parametrize("name,want", [
    ("GND", True), ("+5V", True), ("+3V3", True), ("VBAT_RAW", True),
    ("PGND", True), ("12V", True), ("", True),
    ("SY8089_FB", False), ("U1_N8", False), ("Q1_N5", False), ("EN_12V", False),
])
def test_rail_classification(name, want):
    assert S.is_rail(name) is want


def test_core_and_rail_nets_are_treated_as_rails():
    """电源/地网不能用来做归属附着 —— 规则明确禁止（#58 的 M3 失败原因）。"""
    for rail in ("GND", "+3V3", "VBAT_RAW"):
        assert S.is_rail(rail)


def test_hints_skip_rail_only_peripherals():
    """只连到电源/地的外设（去耦电容）不该拿到 attachTo。"""
    if not ONE_M3.is_file():
        pytest.skip("没有 one-M3.json")
    import json
    src = json.loads(ONE_M3.read_text(encoding="utf-8"))
    hints = S.build_hints(src, 80.0)
    with_attach = [h for h in hints if h.get("attachTo")]
    # 每个带 attachTo 的都必须挂在非电源/地上；反过来说，
    # 不能因为"共享 GND"就给附着提示
    conn = src["connectivity"]
    netname = {n["id"]: (n.get("name") or "") for n in conn["nets"]}
    pin_net = {(x["componentId"], x["pinNumber"]): netname.get(x["netId"], "")
               for x in conn["connections"]}
    for h in with_attach:
        net = pin_net.get((h["componentId"], h["pinNumber"]), "")
        assert not S.is_rail(net), "给电源/地网加了附着提示：%r" % h


def test_selection_uses_two_way_fill_not_width():
    """源码层面钉住：选间距必须用 min(宽比, 高比)。"""
    src = (ROOT / "easycirq" / "scripts" / "sch_layout_spread.py").read_text(
        encoding="utf-8")
    assert "min(w / usable_w, h / usable_h)" in src, \
        "选间距没有按两向填充，会选出细长条"


def test_spread_reports_both_dimensions():
    """输出要同时给占宽和占高，只给宽会掩盖问题。"""
    src = (ROOT / "easycirq" / "scripts" / "sch_layout_spread.py").read_text(
        encoding="utf-8")
    assert "占宽" in src and "占高" in src
