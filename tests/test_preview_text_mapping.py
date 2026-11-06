"""画布 ↔ 页坐标换算的回归测试。

为什么必须有：文字判据只有在**与器件同一坐标系**下才有意义。实测走过两个坑：

  1. 不带 `sheet` 渲染 → 渲染器自己装行，文字在它的 viewBox 里，
     和器件坐标不是一套 → 报出 10 项越页 + 24 项相压，全是**坐标系错位**的假象
  2. 实测 bbox 是**设备像素**，文字锚点是 viewBox 单位，差一个缩放；
     按下标配对还会串行 —— 报出 24 项越页，其实是我把别人的框配给它了

真实换算（用图纸边框矩形做锚点，已用器件本体矩形双向验证）：

    canvas_x = (orig_x - bounds.minX) + ox
    canvas_y = (bounds.maxY - orig_y) + oy
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_preview_text as T  # noqa: E402

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1200"
 viewBox="0 0 1000 600">
<rect x="20" y="85" width="800" height="400"/>
<rect x="220" y="285" width="50" height="40"/>
<text x="220" y="345" font-size="10">U3</text>
</svg>"""
BOUNDS = {"minX": 0, "minY": 0, "maxX": 800, "maxY": 400}


def test_sheet_anchor_found_by_size():
    """锚点由"与 bounds 等大的矩形"确定，不靠猜。"""
    ox, oy = T.sheet_anchor(SVG, BOUNDS)
    assert (ox, oy) == (20.0, 85.0)


def test_round_trip_maps_part_rect_to_itself():
    """器件本体框换算回页坐标后，应与原坐标一致。"""
    ox, oy = T.sheet_anchor(SVG, BOUNDS)

    def to_page_x(cx):
        return cx - ox + BOUNDS["minX"]

    def to_page_y(cy):
        return BOUNDS["maxY"] - (cy - oy)

    # SVG 里那条 rect：x=220 y=285 w=50 h=40（y 向下）
    assert to_page_x(220) == 200.0
    assert to_page_y(285) == 200.0          # 顶边 → 页坐标 y=200
    assert to_page_y(325) == 160.0          # 底边 → 页坐标 y=160


def test_text_anchor_converts_to_page_coordinates():
    ox, oy = T.sheet_anchor(SVG, BOUNDS)
    tx, ty = 220.0, 345.0
    px = tx - ox + BOUNDS["minX"]
    py = BOUNDS["maxY"] - (ty - oy)
    assert px == 200.0 and py == 140.0


def test_convert_refuses_input_without_sheet(tmp_path):
    """没有 sheet.bounds 时必须报错，不许悄悄用别的坐标系。"""
    svg = tmp_path / "a.svg"
    svg.write_text(SVG, encoding="utf-8")
    zones = tmp_path / "z.json"
    zones.write_text(json.dumps({"schemaVersion": 1, "zones": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        T.convert(svg, zones)


def test_convert_filters_decoration_outside_page(tmp_path):
    """页眉/免责声明在图纸外，要按页范围过滤，别冒充"越页"。"""
    svg = tmp_path / "b.svg"
    svg.write_text(SVG.replace(
        "</svg>",
        '<text x="20" y="20" font-size="10">PAGE HEADER</text></svg>'),
        encoding="utf-8")
    zones = tmp_path / "z.json"
    zones.write_text(json.dumps({"schemaVersion": 1,
                                 "zones": [],
                                 "sheet": {"bounds": BOUNDS}}),
                     encoding="utf-8")
    r = T.convert(svg, zones, None, BOUNDS)
    contents = [t["Content"] for t in r["texts"]]
    assert "PAGE HEADER" not in contents, "页眉没被过滤：%r" % contents
    assert "U3" in contents
