"""图签与分区框的回归测试。

放大审图 PNG 后看到两个真问题：
  1. **图签画在图纸外** —— 原来按**图像**右下角定位（`w - tb_w - pad`），
     而图纸有内边距、比例还被封顶，图纸右边界≠图像右边界。
  2. **分区框穿过图签** —— 框铺满可用区后右下角正好压住图签，
     这正是 tokens 里的 `module_frame_overlaps_title_block`。

修法要点：图签矩形收成**只依赖页面**的一个函数（`title_block_page`），
导出端与绘制端共用；分区框两侧共用 `zone_rect` 并在相交时抬下沿。
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"
WORK = ROOT / "reports" / "hard-board" / "board2"


def test_title_block_rect_is_page_only():
    s = REVIEW.read_text(encoding="utf-8")
    assert "def title_block_page(" in s
    i = s.find("def title_block_page(")
    seg = s[i:i + 700]
    assert "sheet" in seg and "TB_SCALE" in seg
    # 不许再按图像宽度定位
    assert "w - tb_w - pad" not in s, "图签还在按图像宽度定位"


def test_zone_rect_is_shared():
    """框算法必须**只有一个**（两处各算一遍会不一致，踩过两次）。"""
    s = REVIEW.read_text(encoding="utf-8")
    assert s.count("def zone_rect(") == 1
    assert s.count("zone_rect(doc, content") >= 2, "导出与绘制都要用它"


def test_frame_avoids_title_block():
    """导出的框必须**不压**图签。"""
    fr = WORK / "review" / "frames-P3_5V转3V3主逻辑轨.json"
    comp = WORK / "composition-M3-placed.json"
    if not fr.is_file() or not comp.is_file():
        pytest.skip("缺产物")
    f = json.loads(fr.read_text(encoding="utf-8"))["frames"][0]["rect"]
    sheet = json.loads(comp.read_text(encoding="utf-8"))["sheet"]
    # 图签在右下角：框的下沿必须高于页面底部的一段距离
    assert f["minY"] > sheet["minY"] + 30, \
        "框的下沿压在了图签区域（minY=%g）" % f["minY"]


def test_zone_ratio_still_within_tokens():
    fr = WORK / "review" / "frames-P3_5V转3V3主逻辑轨.json"
    comp = WORK / "composition-M3-placed.json"
    if not fr.is_file() or not comp.is_file():
        pytest.skip("缺产物")
    f = json.loads(fr.read_text(encoding="utf-8"))["frames"][0]["rect"]
    sh = json.loads(comp.read_text(encoding="utf-8"))["sheet"]
    area = (f["maxX"] - f["minX"]) * (f["maxY"] - f["minY"])
    page = (sh["maxX"] - sh["minX"]) * (sh["maxY"] - sh["minY"])
    r = area / page
    assert 0.25 <= r <= 0.80, "避让图签后分区占比 %.3f 超出 25%%~80%%" % r
