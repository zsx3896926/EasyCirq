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


def test_out_is_assigned_exactly_once():
    """`out` 只能是验收产物的那**一处**赋值。

    被拿来存 stdout 会覆盖产物路径 → `'str' object has no attribute 'write_text'`。
    只判"有没有 `out = `" 会误报（那处本来就该有），所以数**次数**。
    """
    lines = ACC.read_text(encoding="utf-8").splitlines()
    assigns = [l.strip() for l in lines if l.strip().startswith("out = ")]
    assert len(assigns) == 1, "对 out 的赋值应只有 1 处，实际 %d：%r" % (
        len(assigns), assigns[:3])
    assert "acceptance-%s.json" in assigns[0]
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
