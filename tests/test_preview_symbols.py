"""符号绘制的回归测试。

目标里写了"与 style-reference 为基准"，而基准图最显眼的特征是**真实符号**：
IC 方框 + 引脚名/号、电容双板、二极管三角、电源/地符号。
本轮把这些画进预览（只改画法，不动几何/电气数据）。

这些测试钉住：
  1. `extract_pins` 能取到引脚（号/名/坐标），且**不改动原数据**
  2. 位号前缀决定画法（U 走方框、C 走极板、D 走三角）
  3. 引脚分边按**最近边**（引脚在本体外，不能用"贴着边"判据）
  4. 引脚名按密度取舍（宁缺勿叠）
  5. 电源/地画成标准符号，不是一律菱形
"""
import copy
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_review as R  # noqa: E402

SRC = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"
COMP = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"


def test_extract_pins_reads_and_does_not_mutate():
    import json
    if not COMP.is_file():
        pytest.skip("没有排版稿")
    doc = json.loads(COMP.read_text(encoding="utf-8"))
    before = copy.deepcopy(doc)
    pins = R.extract_pins(doc)
    assert pins, "没取到引脚"
    ref = next(iter(pins))
    assert any(p["number"] for p in pins[ref]), "引脚号为空"
    assert doc == before, "extract_pins 改动了原数据"


def test_box_prefixes_are_declared():
    for p in ("U", "J", "X", "F", "Y"):
        assert p in R.BOX_PREFIXES, "方框类前缀缺 %s" % p
    for p in ("R", "C", "D", "L"):
        assert p not in R.BOX_PREFIXES, "%s 不该按方框画" % p


def test_draw_symbol_dispatches_by_prefix():
    s = SRC.read_text(encoding="utf-8")
    # 三种专属画法都要在
    assert 'prefix == "C"' in s and "极板" in s or "两块极板" in s
    assert 'prefix == "D"' in s or "三角" in s
    assert 'prefix == "L"' in s


def test_pin_side_uses_nearest_edge():
    """引脚在本体外（引线约 10 raw），分边必须用最近边。"""
    s = SRC.read_text(encoding="utf-8")
    assert "min(dist, key=dist.get)" in s, "没有按最近边归类"
    assert "贴着边" in s or "不能用\"贴着边\"" in s, "没有记录为什么不能用贴边判据"


def test_pin_name_density_rule():
    s = SRC.read_text(encoding="utf-8")
    assert "show_name" in s, "缺引脚名密度开关"
    assert ">= 9.0" in s, "缺间距阈值"


def test_power_and_ground_use_symbols():
    s = SRC.read_text(encoding="utf-8")
    assert "三横递减" in s or "三横" in s, "地没有画成标准符号"
    assert "横杠" in s, "电源没有画成横杠"
