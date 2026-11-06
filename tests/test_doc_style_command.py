"""产品文档必须写清风格 token 检查的命令与 `--frames` 的真实位置。

实测（#118）：给错路径曾得到 6 项假违规（面积 10.9% vs 真实 73.1%）。
文档不写明位置，使用者必然重踩。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "easycirq" / "references" / "preview-acceptance.md"


def test_doc_has_style_check_command():
    if not DOC.is_file():
        pytest.skip("没有文档")
    s = DOC.read_text(encoding="utf-8")
    assert "sch_style_check.py" in s, "文档没有风格检查命令"
    assert "review/frames-" in s, "没写 frames 的真实位置"


def test_doc_lists_the_frames_trap():
    s = DOC.read_text(encoding="utf-8")
    assert "给错路径会得到假违规" in s
    assert "10.9" in s or "0.00" in s, "没给假违规的具体数字"
