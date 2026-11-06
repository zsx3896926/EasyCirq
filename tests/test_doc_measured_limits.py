"""产品文档必须写清**实测的**不可交付原因（可核对，不是"做不到"四个字）。

#116 的更正：M1 有 16 处、M2 有 3 处导线穿文字。文档若不给数字与复现方式，
读者无法判断"是能力不足还是设计如此"。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "easycirq" / "references" / "preview-acceptance.md"


def test_doc_states_measured_defect_counts():
    if not DOC.is_file():
        pytest.skip("没有文档")
    s = DOC.read_text(encoding="utf-8")
    assert "16 处" in s, "没写 M1 的实测缺陷数"
    assert "3 处" in s, "没写 M2 的实测缺陷数"


def test_doc_records_the_measurement_trap():
    """必须写明：框在 visible.items，不在 texts[]。"""
    s = DOC.read_text(encoding="utf-8")
    assert "visible.items" in s
    assert "bbox" in s


def test_doc_points_at_the_real_gap():
    """必须指出求解输入缺位号框（而不是含糊其辞）。"""
    s = DOC.read_text(encoding="utf-8")
    assert "validateLibRoutingEdge" in s
    assert "求解" in s
