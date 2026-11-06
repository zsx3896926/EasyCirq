"""PNG 门禁第四条：**图形符号贴/压文字**。

目检发现（#122 待办）：`GND` / `+5V` 的网标符号与自己的网名只隔 1 px，
放大看像压在一起。门禁此前只查"文字 vs 文字""导线 vs 文字"，
**符号 vs 文字**没有判据 —— 只有眼睛能发现。

修好后：M3/M4/M5 全部 0 缺陷。
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def _load():
    spec = importlib.util.spec_from_file_location("rev_sym", str(REVIEW))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_helper_exists():
    s = REVIEW.read_text(encoding="utf-8")
    assert "def count_symbol_text_hits(" in s
    assert "symbolTextHits" in s


def test_detects_symbol_touching_text():
    m = _load()
    symbols = [(100, 100, 114, 111)]          # 地符号框
    texts = [("GND", (115, 105, 145, 115))]   # 与符号相距 1 px
    assert len(m.count_symbol_text_hits(symbols, texts, 800, 600, None)) == 1


def test_clear_symbol_is_fine():
    m = _load()
    symbols = [(100, 100, 114, 111)]
    texts = [("GND", (160, 105, 190, 115))]   # 相距 46 px
    assert m.count_symbol_text_hits(symbols, texts, 800, 600, None) == []


def test_gate_fails_on_symbol_text():
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find('q["problems"].append("符号贴近文字')
    assert i > 0, "没把符号判据并入结论"
    assert 'q["verdict"] = "fail"' in s[i:i + 400]


def test_searches_avoid_symbols():
    """位号与网标两处搜索都要把符号框当障碍。"""
    s = REVIEW.read_text(encoding="utf-8")
    assert s.count("+ list(symbol_boxes)") == 2
