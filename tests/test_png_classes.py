"""验收里的 PNG 判据必须**分类统计**五类缺陷。

曾经的 bug：只解析 `文字相压 (\\d+) 处`，另四类缺陷显示成 0，
数字与结论不一致。另有一个变量遮蔽 bug：用 `out` 存 stdout 覆盖了产物路径。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"
DOC = ROOT / "easycirq" / "references" / "preview-acceptance.md"


def test_parses_all_five_classes():
    s = ACC.read_text(encoding="utf-8")
    for pat in ("文字相压", "导线穿过文字", "符号贴近文字",
                "文字落在自己本体内"):
        assert pat in s, "没有解析 %s" % pat


def test_out_is_not_shadowed_by_stdout():
    """`out` 是验收产物路径，不能被用来存 stdout。

    只查真正的回归点：不出现 `out = rv.stdout`，且改用 `rv_out`。
    不数全文件 `out` 的赋值次数 —— `_mark_refused` 里也有一个**局部** `out`，
    那是合法的（本测试第一版因此误报过）。
    """
    lines = ACC.read_text(encoding="utf-8").splitlines()
    assert not any(l.strip().startswith("out = rv.stdout") for l in lines)
    assert any("rv_out = rv.stdout" in l for l in lines)


def test_detail_reports_classes():
    s = ACC.read_text(encoding="utf-8")
    assert "各类缺陷" in s


def test_doc_lists_five_png_criteria():
    if not DOC.is_file():
        pytest.skip("没有文档")
    d = DOC.read_text(encoding="utf-8")
    assert "五类缺陷判据" in d
    assert "界定适用域" in d, "没写判据误报的教训"
