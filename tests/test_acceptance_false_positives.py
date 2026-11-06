"""已知误报判定的回归测试。

两类误报必须被正确豁免，**同时不许滥用豁免**：

  • `pin_name_inside_body` —— 引脚名画在自己本体内（箱形符号正常画法）
  • `designator_at_corner` —— 位号写在符号角上（预览渲染器的排版约定）

红线：内容只是**碰巧等于**某个引脚名/位号、但既不在该器件框内也不在其角上时，
**不许**豁免 —— 那就是把真缺陷当误报放过去。
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_acceptance as A  # noqa: E402

COMP = {"id": "c33", "bbox": [250.0, 140.0, 300.0, 180.0]}
OTHER = {"id": "c99", "bbox": [500.0, 400.0, 560.0, 440.0]}


def src_with(texts, pins=(("U3-EN", 240.0, 150.0),)):
    return {
        "components": [COMP, OTHER],
        "texts": texts,
        "attachment_points": [{"id": i, "x": x, "y": y, "kind": "pin"}
                              for i, x, y in pins],
    }


def finding(comp, text):
    return {"code": "bbox_overlap", "objects": [comp, text]}


def test_pin_name_inside_body_is_exempt():
    """EN 是本器件引脚名、落在框内 → 误报。"""
    src = src_with([{"id": "t1", "bbox": [252, 148, 259, 152], "content": "EN"}])
    kept, ex = A._pin_name_false_positives([finding("c33", "t1")], src)
    assert kept == [] and len(ex) == 1
    assert ex[0]["exempt_reason"] == "pin_name_inside_body"


def test_designator_at_corner_is_exempt():
    """U3 是本器件位号、贴在角上（可在框外）→ 误报。"""
    src = src_with([{"id": "t2", "bbox": [250, 182, 259, 190], "content": "U3"}],
                   pins=())
    kept, ex = A._pin_name_false_positives(
        [finding("c33", "t2")], src, owners={"c33": "U3"})
    assert kept == [] and len(ex) == 1
    assert ex[0]["exempt_reason"] == "designator_at_corner"


def test_stranger_text_is_not_exempt():
    """内容是 U3 的引脚名，但位置在**别的**器件上 —— 不许豁免。"""
    src = src_with([{"id": "t3", "bbox": [520, 410, 530, 420], "content": "EN"}])
    kept, ex = A._pin_name_false_positives([finding("c99", "t3")], src)
    assert len(kept) == 1 and ex == [], "把真缺陷误判成误报了"


def test_wrong_content_is_not_exempt():
    """位置对但内容不是该器件的引脚名/位号 —— 不许豁免。"""
    src = src_with([{"id": "t4", "bbox": [252, 148, 259, 152], "content": "XYZ"}])
    kept, ex = A._pin_name_false_positives([finding("c33", "t4")], src)
    assert len(kept) == 1 and ex == []


def test_designator_far_from_corner_is_not_exempt():
    """位号内容对、但离角很远（可能真溢出）—— 不许豁免。"""
    src = src_with([{"id": "t5", "bbox": [330, 210, 360, 220], "content": "U3"}],
                   pins=())
    kept, ex = A._pin_name_false_positives(
        [finding("c33", "t5")], src, owners={"c33": "U3"})
    assert len(kept) == 1 and ex == []


def test_missing_owners_skips_corner_rule_without_guessing():
    """没有 owners 时跳过角标判定，宁可漏豁免也不误豁免。"""
    src = src_with([{"id": "t6", "bbox": [250, 182, 259, 190], "content": "U3"}],
                   pins=())
    kept, ex = A._pin_name_false_positives([finding("c33", "t6")], src)
    assert len(kept) == 1 and ex == []


@pytest.mark.parametrize("code", ["bbox_overlap", "wire_enters_bbox"])
def test_only_these_codes_are_exemptible(code):
    src = src_with([{"id": "t7", "bbox": [252, 148, 259, 152], "content": "EN"}])
    f = {"code": code, "objects": ["c33", "t7"]}
    kept, ex = A._pin_name_false_positives([f], src)
    assert len(ex) == 1


def test_other_codes_never_exempted():
    src = src_with([{"id": "t8", "bbox": [252, 148, 259, 152], "content": "EN"}])
    f = {"code": "different_named_wires_cross", "objects": ["c33", "t8"]}
    kept, ex = A._pin_name_false_positives([f], src)
    assert len(kept) == 1 and ex == []
