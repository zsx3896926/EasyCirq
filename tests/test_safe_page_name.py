"""文件名净化：两边必须**同一套规则**。

否则渲染器写的名字与驱动要找的名字不一致 → PNG 判据静默变 NOT RUN。
（本轮实测：净化后验收从 9 PASS 掉到 8 PASS / 2 N/R。）
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"
ACC = ROOT / "easycirq" / "scripts" / "sch_preview_accept.py"

CASES = [
    "P4_输入保护与滤波",
    "P3_5V → 3.3V 主逻辑轨（SY8089）",
    "P5_升降压：5V → 3.8V（TPS63802）",
    "a/b:c (d)",
    "",
]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_both_sides_agree():
    rv = _load("rv_name", REVIEW)
    ac = _load("ac_name", ACC)
    for c in CASES:
        assert rv.safe_name(c) == ac.safe_page_name(c), c


def test_names_are_filesystem_safe():
    rv = _load("rv_name2", REVIEW)
    for c in CASES:
        n = rv.safe_name(c)
        for bad in (" ", "→", "（", "）", ":", "/", "\\"):
            assert bad not in n, "%r 仍含 %r" % (n, bad)
        assert n, "不能为空"


def test_safe_name_keeps_chinese():
    rv = _load("rv_name3", REVIEW)
    assert "输入保护与滤波" in rv.safe_name("P4_输入保护与滤波")
