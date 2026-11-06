"""位号预留区（textBboxes）的回归测试。

本轮实测结论（真实输出）：

  开启 `--designator-reserve`：
    M3/M4/M5 ✅ 可解（1.2 / 1.3 / 0.3 秒），路由器确实避开导线穿位号
    M1      ❌ 40 万候选内解不出（关闭时 8 秒解出）
    M2      ❌ 40 万候选内解不出
    渲染阶段 ❌ `component label reservation collision: C13/U3`

所以**默认关闭**：能力可用，但"位号与位号之间的预留区互相避让"没做之前，
密集模块不能开——开着会把原本能解的板子弄坏。

这些测试钉住：
  1. 默认不产 textBboxes（不写空数组，也不写键）
  2. 开启时按渲染器规则给出位号框（本体左上角上方、字号 7）
  3. 关掉后输入里**完全不出现** textBboxes 键
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_input as L  # noqa: E402

NET = ROOT / "reports" / "hard-board" / "board2" / "netlist.json"
MEA = ROOT / "reports" / "hard-board" / "board2" / "measurements.json"
PLAN = ROOT / "reports" / "hard-board" / "board2" / "page-plan.json"


def _build(tmp_path, reserve):
    if not NET.is_file() or not MEA.is_file():
        pytest.skip("缺网表或测量输入")
    out = tmp_path / "in.json"
    plans = [PLAN] if PLAN.is_file() else []
    src, problems = L.build(NET, MEA, plans, out, max_candidates=1000,
                            designator_reserve=reserve)
    return src


def test_default_does_not_emit_text_boxes(tmp_path):
    """默认关闭：measurements 里不许出现 textBboxes 键。"""
    src = _build(tmp_path, False)
    for m in src.get("measurements") or []:
        assert "textBboxes" not in m, "关闭时仍写了 textBboxes：%r" % m.get("designator")


def test_reserve_emits_boxes_per_designator(tmp_path):
    src = _build(tmp_path, True)
    boxes = [m for m in (src.get("measurements") or []) if m.get("textBboxes")]
    if not boxes:
        pytest.skip("该页没有器件")
    for m in boxes:
        b = m["textBboxes"][0]
        body = m["bbox"]
        # 位号画在本体左上角上方（渲染器规则），所以框的下沿在本体上沿之上
        assert b["minY"] >= body["maxY"] - 2.0, "位号框没在本体上方：%r" % b
        assert b["maxX"] > b["minX"] and b["maxY"] > b["minY"]


def test_box_width_scales_with_designator_length(tmp_path):
    """位号越长，预留区越宽（不能用一个常数糊过去）。"""
    src = _build(tmp_path, True)
    pairs = {}
    for m in src.get("measurements") or []:
        tb = m.get("textBboxes")
        if tb:
            pairs[m["designator"]] = tb[0]["maxX"] - tb[0]["minX"]
    if len(pairs) < 2:
        pytest.skip("器件不足")
    longest = max(pairs, key=len)
    shortest = min(pairs, key=len)
    if len(longest) == len(shortest):
        pytest.skip("位号长度相同")
    assert pairs[longest] > pairs[shortest], \
        "位号长度不同但预留宽度相同：%r" % pairs
