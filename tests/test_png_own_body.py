"""PNG 门禁第五条：**位号落在自己本体内**。

目检时我怀疑 M5 的 `L5` 位号压在自己的本体上；**用数据核实后是错的** ——
文字在 (378,176)，本体 y∈[165,175]，明明在本体**上方**。肉眼误判。

判据仍然值得留：它防的是真实的一类错误（位号掉进符号里）。
关键约束：**只查位号**，不查引脚名 —— 引脚名本来就画在符号内部
（PG/FB/VOUT/EN…），第一版没区分，一下误报 5/9/10 处。
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def _load():
    spec = importlib.util.spec_from_file_location("rev_own", str(REVIEW))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_helper_exists():
    s = REVIEW.read_text(encoding="utf-8")
    assert "def count_text_in_own_body(" in s
    assert "textInOwnBody" in s


def test_detects_designator_inside_body():
    m = _load()
    texts = [("R14", (110, 110, 130, 120))]
    bodies = [(100, 100, 200, 150)]
    hits = m.count_text_in_own_body(texts, bodies, 800, 600, None,
                                   designators={"R14"})
    assert len(hits) == 1


def test_pin_names_inside_body_are_fine():
    """引脚名画在符号里是标准画法，不能报。"""
    m = _load()
    texts = [("VOUT", (110, 110, 140, 120)), ("EN", (112, 130, 122, 140))]
    bodies = [(100, 100, 200, 150)]
    assert m.count_text_in_own_body(texts, bodies, 800, 600, None,
                                    designators={"U3"}) == []


def test_outside_body_is_fine():
    m = _load()
    texts = [("R14", (110, 160, 130, 170))]      # 在本体上方
    bodies = [(100, 100, 200, 150)]
    assert m.count_text_in_own_body(texts, bodies, 800, 600, None,
                                    designators={"R14"}) == []


def test_gate_fails_on_own_body():
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find('q["problems"].append("文字落在自己本体内')
    assert i > 0
    assert 'q["verdict"] = "fail"' in s[i:i + 400]
