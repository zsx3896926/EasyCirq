"""PNG 门禁再加一条：**导线穿过文字**。

SVG 侧一直有 `wire_enters_bbox`；PNG 侧此前只查"文字相压"，
所以"导线从标签中间穿过去"只有看图才能发现。

新判据立刻抓到 3 处：M3 的 `+5V`、M4 的 `GND` 与 `+5V`。
给网标文字加四向（后扩到六向）搜索后：M3、M5 清零，**M4 剩 1 处**。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rev3", str(REVIEW))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_wire_text_helper_exists():
    s = REVIEW.read_text(encoding="utf-8")
    assert "def count_wire_text_hits(" in s
    assert "wireTextHits" in s


def test_detects_wire_through_text():
    m = _load()
    texts = [("GND", (100, 100, 140, 110))]
    segs = [((120, 50), (120, 200))]        # 竖线穿过文字框
    hits = m.count_wire_text_hits(texts, segs, 800, 600, None)
    assert len(hits) == 1
    assert hits[0]["text"] == "GND"


def test_clean_wire_is_fine():
    m = _load()
    texts = [("GND", (100, 100, 140, 110))]
    segs = [((300, 50), (300, 200))]        # 离文字很远
    assert m.count_wire_text_hits(texts, segs, 800, 600, None) == []


def test_gate_fails_on_wire_text():
    s = REVIEW.read_text(encoding="utf-8")
    # 定位**处理处**（problems 里那一句），不是 docstring 里的同名文字
    i = s.find('q["problems"].append("导线穿过文字')
    assert i > 0
    seg = s[i:i + 900]   # 窗口要够宽：verdict 那行在几行之后
    assert 'q["verdict"] = "fail"' in seg


def test_net_label_has_multiple_candidates():
    """网标文字必须有多向候选（固定一侧会被导线穿过）。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("cand_xy = (")
    assert i > 0
    seg = s[i:i + 700]
    assert seg.count("cxp") >= 4, "网标候选太少"
