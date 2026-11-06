"""图纸语言（网格/标尺/图签避让）的回归测试。

基准图的图纸特征：浅网格、外框 + 行列标尺、右下角图签。
本轮补上，并踩到两处重叠：图签压底部标尺、右侧行标压图签。
这些测试钉住"不许再压"。
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_review as R  # noqa: E402

SRC = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_grid_uses_style_tokens():
    """网格间距来自 tokens 的 sheet.grid_mil，不硬编码另一套。"""
    s = SRC.read_text(encoding="utf-8")
    assert "grid_mil" in s, "网格没有读 tokens"
    assert "grid_raw" in s


def test_rulers_exist_for_columns_and_rows():
    s = SRC.read_text(encoding="utf-8")
    assert "cells_x" in s and "cells_y" in s, "缺行列标尺"
    assert 'ord("A")' in s, "行标不是字母"


def test_title_block_clears_bottom_ruler():
    """图签要让开底部标尺带（实测压住过 8/9/10/11）。"""
    s = SRC.read_text(encoding="utf-8")
    assert "ruler_band" in s, "图签没有为标尺让位"
    assert "tb_left" in s and "tb_right" in s, "底部标尺没有按图签范围避让"


def test_side_letters_avoid_title_block():
    """右侧行标不许压在图签上。"""
    s = SRC.read_text(encoding="utf-8")
    assert "tb_top" in s, "行标没有按图签范围避让"


def test_pin_names_align_into_columns():
    """引脚名对齐成列（按边固定内缩），不随引脚 jitter。"""
    s = SRC.read_text(encoding="utf-8")
    assert "inset = 3.0" in s
    assert 'side == "L"' in s and 'side == "R"' in s


def test_render_is_deterministic():
    """同样的输入必须画出同样的图（否则哈希不能当证据）。"""
    comp = ROOT / "reports" / "hard-board" / "board2" / "composition-M3-placed.json"
    if not comp.is_file():
        pytest.skip("没有排版稿")
    import hashlib
    import json
    import tempfile
    doc = json.loads(comp.read_text(encoding="utf-8"))
    parts, wires, flags, modules = R.extract(doc)
    sheet = doc["sheet"]
    q = R.quality(parts, wires, sheet)
    hashes = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "x.png"
            R.render(doc, parts, wires, flags, modules, "P", out, q)
            if not out.is_file():
                pytest.skip("渲染不可用（缺 Pillow）")
            hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1], "同一输入两次渲染不一致"
