"""PNG 图签字段必须与 SVG/样图**对齐**。

发现：SVG 图签是 6 字段（含 SIZE），而 **PNG** 图签只有 5 行、**没有尺寸** ——
PNG 才是交付物。参考样图（esp32-schematic.png）的图签也有尺寸、设计、审核。
两边字段集不一致本身就是缺陷：读图的人拿不到图纸尺寸。
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_png_title_block_has_size_and_reviewer():
    s = REVIEW.read_text(encoding="utf-8")
    assert '("尺寸"' in s, "PNG 图签缺尺寸"
    assert '("审核"' in s, "PNG 图签缺审核"


def test_png_title_block_keeps_token_fields():
    """token 要求的 6 项在图签里都要能对上（图名/版本/页/日期/尺寸）。"""
    s = REVIEW.read_text(encoding="utf-8")
    for key in ('"图名"', '"版本"', '"页"', '"日期"', '"尺寸"'):
        assert key.replace('"', '("').replace("(", "(", 1) in s or key in s
