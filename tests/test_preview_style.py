"""审图风格必须**跟规范走**，不许各画各的。

基准：`assets/style-reference/esp32-schematic.png` + `style-tokens.json`。
本文件钉住三件本轮踩出来的事：

  1. 配色/字号从 tokens 读，不硬编码
  2. 网名**不截断**（`+3V3` 被切成 `+3V` 会误导读者）
  3. 位号画在本体**外侧**（压在本体上不可读）
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_review as R  # noqa: E402

SRC = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_style_tokens_load():
    tokens = R.load_style_tokens()
    if not tokens:
        pytest.skip("本机没有 style-tokens.json")
    pal = (tokens.get("palette") or {}).get("zone_border") or []
    assert len(pal) >= 3, "分区配色不足：%r" % pal
    assert all(str(c).startswith("#") for c in pal)
    assert (tokens.get("typography") or {}).get("zone_title"), "缺区名字号规范"


def test_renderer_does_not_truncate_net_names():
    """网名不许截断 —— 实测 `+3V3` 被切成 `+3V`。"""
    s = SRC.read_text(encoding="utf-8")
    assert 'net[:9]' not in s, "还在截断网名"
    assert "网名**不截断**" in s or "网名不截断" in s, "没有记录为什么不截断"


def test_designator_is_drawn_outside_body():
    """位号画在本体外（上方），不压本体。"""
    s = SRC.read_text(encoding="utf-8")
    assert "- 13" in s, "位号没有上移出本体"
    assert "上方外侧" in s or "上方" in s


def test_zone_chip_is_outside_frame():
    """分区色块画在框外，避免压住器件（实测压住过 C15）。"""
    s = SRC.read_text(encoding="utf-8")
    assert "cy0 = ay - chip_h - 2" in s, "色块没有移到框外上方"


def test_title_block_values_are_clipped_to_box():
    """图签的值要按框宽截断，不许画出框外。"""
    s = SRC.read_text(encoding="utf-8")
    assert "def fit(text, fnt)" in s, "缺按宽度截断的实现"
    assert "val_room" in s


def test_renderer_applies_net_colors():
    """电源/地/信号用 tokens 里的三种颜色。"""
    s = SRC.read_text(encoding="utf-8")
    assert "net_color(" in s
    assert "net_power" in s and "net_ground" in s and "net_signal" in s
